# This file is part of Jeedom.
#
# Jeedom is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Jeedom is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Jeedom. If not, see <http://www.gnu.org/licenses/>.

"""
Démon du plugin esphomebe.

Il tient une connexion permanente à chaque module ESPHome par l'API native
(port 6053, chiffrée par la clé du module), et repousse vers Jeedom ce que le
module annonce : sa description, la liste de ses entités, puis chaque
changement d'état.

Tout le protocole est délégué à aioesphomeapi, la bibliothèque qu'utilise
Home Assistant : chiffrement Noise, reconnexion, délai croissant entre les
tentatives. Ce fichier ne fait que la traduction vers Jeedom.

Le démon ne charge pas le coeur de Jeedom. Il reçoit sa configuration par le
callback du plugin, et y renvoie ses événements par lots :
    GET  <callback>?apikey=…&action=config
    POST <callback>?apikey=…   {"events": […]}

Les ordres de Jeedom arrivent sur un port local, une ligne JSON par ordre, la
clé API du plugin en guise de mot de passe.
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import urllib.error
import urllib.parse
import urllib.request

from aioesphomeapi import APIClient, ReconnectLogic
from aioesphomeapi.core import InvalidEncryptionKeyAPIError, RequiresEncryptionAPIError

import catalog

LOG = logging.getLogger('esphomebed')

# Au-delà, les événements les plus anciens sont abandonnés : Jeedom injoignable
# pendant des heures ne doit pas faire gonfler la mémoire du démon sans fin.
QUEUE_LIMIT = 2000

# Les états arrivent par rafales (une douzaine à la connexion) : on les groupe
# pour ne faire qu'une requête HTTP par rafale.
FLUSH_DELAY = 0.3

# Un lot que Jeedom a reçu mais refusé (erreur PHP, réponse autre que OK) est
# abandonné après ce nombre d'essais. Le garder indéfiniment en tête de file
# bloquerait tous les suivants : plus aucune valeur ne remonterait.
MAX_REJECTIONS = 3

# Codes HTTP d'un Apache en redémarrage ou en maintenance : Jeedom n'a pas
# refusé le lot, il n'a pas pu le lire. On garde et on réessaie.
TRANSIENT_HTTP = (502, 503, 504)


class Link:
    """Le lien vers Jeedom : configuration à l'aller, événements au retour."""

    def __init__(self, callback, apikey):
        self.callback = callback
        self.apikey = apikey
        self.queue = []
        self.wakeup = asyncio.Event()

    def _url(self, params):
        params = dict(params, apikey=self.apikey)
        sep = '&' if '?' in self.callback else '?'
        return self.callback + sep + urllib.parse.urlencode(params)

    def _get(self, params):
        with urllib.request.urlopen(self._url(params), timeout=15) as answer:
            return answer.read().decode('utf-8')

    def _post(self, events):
        body = json.dumps({'events': events}).encode('utf-8')
        request = urllib.request.Request(self._url({}), data=body,
                                         headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=15) as answer:
            return answer.read().decode('utf-8').strip()

    async def fetch_config(self):
        """La configuration, relue jusqu'à obtention : sans elle, rien à faire."""
        delay = 2
        while True:
            try:
                text = await asyncio.to_thread(self._get, {'action': 'config'})
                return json.loads(text)
            except Exception as err:  # noqa: BLE001 — tout échec mène à la même attente
                LOG.warning('Configuration illisible (%s), nouvel essai dans %ss', err, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)

    def send(self, event):
        self.queue.append(event)
        self._trim()
        self.wakeup.set()

    def _trim(self):
        if len(self.queue) > QUEUE_LIMIT:
            dropped = len(self.queue) - QUEUE_LIMIT
            del self.queue[:dropped]
            LOG.warning('%s événements abandonnés : Jeedom ne les prend plus', dropped)

    async def run(self):
        """
        Envoie les lots. Le lot en vol est sorti de la file : ce qui arrive
        pendant l'envoi s'accumule derrière, et un échec le remet devant.
        """
        rejections = 0
        while True:
            await self.wakeup.wait()
            await asyncio.sleep(FLUSH_DELAY)
            self.wakeup.clear()
            if not self.queue:
                continue
            batch, self.queue = self.queue, []
            try:
                answer = await asyncio.to_thread(self._post, batch)
                if answer != 'OK':
                    raise ValueError('réponse de Jeedom : ' + answer[:200])
                rejections = 0
                continue
            except urllib.error.HTTPError as err:
                refused = err.code not in TRANSIENT_HTTP
                reason = 'HTTP %s' % err.code
            except ValueError as err:
                refused = True
                reason = str(err)
            except Exception as err:  # noqa: BLE001 — Jeedom injoignable : on garde tout
                refused = False
                reason = str(err)

            if refused:
                rejections += 1
                if rejections >= MAX_REJECTIONS:
                    LOG.error('Lot de %d événements refusé %d fois par Jeedom (%s) : abandonné. '
                              'Voir /var/www/html/log/http.error', len(batch), rejections, reason)
                    rejections = 0
                    self.wakeup.set()
                    continue
            LOG.error('Envoi à Jeedom impossible (%s), nouvel essai dans 10s', reason)
            self.queue = batch + self.queue
            self._trim()
            await asyncio.sleep(10)
            self.wakeup.set()


class Device:
    """Un module ESPHome, et la connexion qui le suit."""

    def __init__(self, link, conf):
        self.link = link
        self.conf = conf
        self.id = conf['id']
        self.label = conf.get('name') or conf['host']
        self.state = 'déconnecté'
        self.error = ''
        self.entities = {}      # clé ESPHome → description de l'entité
        self.by_logical = {}    # identifiant Jeedom → description de l'entité
        self.client = None
        self.logic = None

    def signature(self):
        """Ce qui, s'il change, impose de rouvrir la connexion."""
        return (self.conf['host'], int(self.conf.get('port') or 6053), self.conf.get('key') or '')

    async def start(self):
        self.client = APIClient(
            self.conf['host'],
            int(self.conf.get('port') or 6053),
            None,
            noise_psk=self.conf.get('key') or None,
            client_info='Jeedom esphomebe',
        )
        self.logic = ReconnectLogic(
            client=self.client,
            on_connect=self._on_connect,
            on_disconnect=self._on_disconnect,
            on_connect_error=self._on_connect_error,
            # Le nom sert à écouter les annonces mDNS du module : inutile, et
            # même trompeur, quand on s'y connecte par son adresse IP.
            name=None,
        )
        self.state = 'connexion'
        await self.logic.start()

    async def stop(self):
        if self.logic is not None:
            await self.logic.stop()
        if self.client is not None:
            try:
                await self.client.disconnect()
            except Exception:  # noqa: BLE001 — on s'en va de toute façon
                pass
        self.state = 'arrêté'

    async def _on_connect(self):
        """
        Une erreur ici n'est pas rattrapée par la bibliothèque : elle tient la
        connexion pour établie, et le module resterait connecté sans jamais
        rien envoyer. On coupe donc nous-mêmes, pour qu'elle reprenne.
        """
        try:
            await self._describe_and_subscribe()
        except Exception as err:  # noqa: BLE001
            LOG.error('%s : lecture du module impossible (%s), reconnexion', self.label, err)
            self.state = 'en erreur'
            self.error = 'lecture du module impossible : %s' % (str(err) or type(err).__name__)
            self.link.send({'type': 'status', 'eq_id': self.id, 'status': 'disconnected',
                            'error': self.error})
            await self.client.disconnect(force=True)

    async def _describe_and_subscribe(self):
        info = await self.client.device_info()
        entities, _services = await self.client.list_entities_services()

        self.entities.clear()
        self.by_logical.clear()
        described = []
        unsupported = []
        for entity in entities:
            result = catalog.describe(entity)
            if result is None:
                unsupported.append({'type': type(entity).__name__.replace('Info', ''),
                                    'name': entity.name, 'object_id': entity.object_id})
                continue
            domain, commands = result
            base = domain + '::' + entity.object_id
            if base in self.by_logical:
                # Deux sous-appareils peuvent porter une entité du même nom :
                # la seconde prend le numéro de son sous-appareil.
                base += '_%s' % (entity.device_id or entity.key)
            for command in commands:
                command['logical_id'] = base + ('::' + command['field'] if command['field'] else '')
                if command.get('value') is not None:
                    # Le retour d'état d'une action : l'info qu'elle modifie.
                    command['value'] = base + ('::' + command['value'] if command['value'] else '')
            description = {
                'domain': domain,
                'logical_id': base,
                'object_id': entity.object_id,
                # Une entité sans nom porte celui du module (convention ESPHome
                # depuis friendly_name).
                'name': entity.name or info.friendly_name or info.name,
                'disabled_by_default': entity.disabled_by_default,
                'entity_category': int(entity.entity_category),
                'device_class': getattr(entity, 'device_class', '') or '',
                'commands': commands,
            }
            self.entities[entity.key] = (domain, entity, base)
            self.by_logical[base] = (domain, entity)
            described.append(description)

        self.link.send({
            'type': 'device',
            'eq_id': self.id,
            'info': {
                'name': info.name,
                'friendly_name': info.friendly_name,
                'mac': info.mac_address,
                'model': info.model,
                'manufacturer': info.manufacturer,
                'esphome_version': info.esphome_version,
                'compilation_time': info.compilation_time,
                'project_name': info.project_name,
                'project_version': info.project_version,
            },
            'entities': described,
            'unsupported': unsupported,
        })

        self.state = 'connecté'
        self.error = ''
        self.link.send({'type': 'status', 'eq_id': self.id, 'status': 'connected',
                        'esphome_version': info.esphome_version})
        LOG.info('%s : connecté (%s, ESPHome %s, %d entités)', self.label, info.name,
                 info.esphome_version, len(described))

        self.client.subscribe_states(self._on_state)

    async def _on_disconnect(self, expected):
        self.state = 'déconnecté'
        self.link.send({'type': 'status', 'eq_id': self.id, 'status': 'disconnected',
                        'error': '' if expected else 'connexion perdue'})
        LOG.info('%s : déconnecté%s', self.label, '' if expected else ' (inattendu)')

    async def _on_connect_error(self, err):
        # Une mauvaise clé ne se corrige pas en réessayant : le dire clairement,
        # une fois par changement de message, plutôt qu'à chaque tentative.
        if isinstance(err, InvalidEncryptionKeyAPIError):
            message = 'clé API refusée par le module'
        elif isinstance(err, RequiresEncryptionAPIError):
            message = 'le module exige une clé API'
        else:
            message = str(err) or type(err).__name__
        self.state = 'en erreur'
        if message != self.error:
            self.error = message
            LOG.warning('%s : %s', self.label, message)
            self.link.send({'type': 'status', 'eq_id': self.id, 'status': 'disconnected',
                            'error': message})

    def _on_state(self, state):
        known = self.entities.get(state.key)
        if known is None:
            return
        domain, entity, base = known
        try:
            fields = catalog.values(domain, entity, state)
        except Exception as err:  # noqa: BLE001 — un état bizarre ne doit pas couper la connexion
            LOG.warning('%s : état illisible pour %s (%s)', self.label, base, err)
            return
        for field, value in fields.items():
            if value is None:
                continue
            self.link.send({'type': 'state', 'eq_id': self.id,
                            'logical_id': base + ('::' + field if field else ''), 'value': value})

    def command(self, logical_id, action, value):
        """Exécute une commande action. Lève une exception si c'est impossible."""
        if self.state != 'connecté':
            raise RuntimeError('le module n\'est pas connecté')
        known = self.by_logical.get(logical_id)
        if known is None:
            raise RuntimeError('entité inconnue : ' + logical_id)
        domain, entity = known
        LOG.debug('%s : %s → %s %r', self.label, logical_id, action, value)
        catalog.run(self.client, domain, entity, action, value)

    def status(self):
        return {'id': self.id, 'name': self.label, 'host': self.conf['host'],
                'state': self.state, 'error': self.error, 'entities': len(self.entities)}


class Daemon:

    def __init__(self, args, apikey):
        self.args = args
        self.apikey = apikey
        self.link = Link(args.callback, apikey)
        self.devices = {}
        self.stopping = asyncio.Event()
        # Un rechargement peut arriver pendant la configuration initiale, ou
        # pendant une reconnexion : les deux ouvriraient la même connexion.
        self.lock = asyncio.Lock()

    async def apply_config(self, config):
        """Aligne les connexions sur la configuration, sans toucher à ce qui n'a pas changé."""
        async with self.lock:
            await self._apply_config(config)

    async def _apply_config(self, config):
        wanted = {int(d['id']): d for d in config.get('devices', [])}

        for eq_id in list(self.devices):
            device = self.devices[eq_id]
            conf = wanted.get(eq_id)
            if conf is None or Device(self.link, conf).signature() != device.signature():
                LOG.info('%s : connexion fermée (retiré ou modifié)', device.label)
                await device.stop()
                del self.devices[eq_id]
            else:
                device.conf = conf
                device.label = conf.get('name') or conf['host']

        for eq_id, conf in wanted.items():
            if eq_id not in self.devices:
                device = Device(self.link, conf)
                self.devices[eq_id] = device
                LOG.info('%s : ouverture de la connexion vers %s', device.label, conf['host'])
                await device.start()

    async def handle_order(self, reader, writer):
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=5)
            order = json.loads(line.decode('utf-8') or '{}')
            if order.get('apikey') != self.apikey:
                LOG.error('Ordre refusé : clé API invalide')
                answer = {'state': 'error', 'result': 'clé API invalide'}
            else:
                answer = {'state': 'ok', 'result': await self.execute(order)}
        except Exception as err:  # noqa: BLE001 — l'erreur est rendue à l'appelant
            answer = {'state': 'error', 'result': str(err)}
        try:
            writer.write((json.dumps(answer) + '\n').encode('utf-8'))
            await writer.drain()
        finally:
            writer.close()

    async def execute(self, order):
        name = order.get('order')
        LOG.debug('Ordre reçu : %s', name)
        if name == 'reload':
            await self.apply_config(await self.link.fetch_config())
            return 'reloaded'
        if name == 'status':
            return {'devices': [d.status() for d in self.devices.values()]}
        if name == 'command':
            device = self.devices.get(int(order.get('id', 0)))
            if device is None:
                raise RuntimeError('module inconnu du démon')
            device.command(order.get('logical_id', ''), order.get('action', ''), order.get('value'))
            return 'sent'
        if name == 'reconnect':
            async with self.lock:
                device = self.devices.pop(int(order.get('id', 0)), None)
                if device is None:
                    raise RuntimeError('module inconnu du démon')
                conf = device.conf
                await device.stop()
                self.devices[conf['id']] = Device(self.link, conf)
                await self.devices[conf['id']].start()
            return 'reconnecting'
        raise RuntimeError('ordre inconnu : %s' % name)

    async def run(self):
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self.stopping.set)

        server = await asyncio.start_server(self.handle_order, '127.0.0.1', self.args.socketport)
        LOG.info('Démon à l\'écoute des ordres sur 127.0.0.1:%s', self.args.socketport)
        sender = asyncio.create_task(self.link.run())

        await self.apply_config(await self.link.fetch_config())
        await self.stopping.wait()

        LOG.info('Arrêt du démon')
        server.close()
        for device in list(self.devices.values()):
            await device.stop()
        sender.cancel()


def main():
    parser = argparse.ArgumentParser(description='Démon ESPHome pour Jeedom')
    parser.add_argument('--callback', required=True)
    parser.add_argument('--pid', required=True)
    parser.add_argument('--socketport', type=int, default=55063)
    parser.add_argument('--loglevel', default='error')
    args = parser.parse_args()

    level = {'debug': logging.DEBUG, 'info': logging.INFO, 'warning': logging.WARNING,
             'notice': logging.INFO, 'error': logging.ERROR, 'none': logging.CRITICAL}
    logging.basicConfig(level=level.get(args.loglevel.lower(), logging.ERROR),
                        format='[%(asctime)s][%(levelname)s] %(name)s : %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S', stream=sys.stdout)
    # La bibliothèque est bavarde au niveau info : on ne garde que ses alertes,
    # sauf en débogage.
    if args.loglevel.lower() != 'debug':
        logging.getLogger('aioesphomeapi').setLevel(logging.WARNING)

    # La clé API arrive par l'entrée standard : la ligne de commande est
    # lisible par n'importe quel utilisateur local avec ps.
    apikey = sys.stdin.readline().strip()
    if apikey == '':
        LOG.error('Aucune clé API reçue sur l\'entrée standard')
        sys.exit(1)

    with open(args.pid, 'w') as handle:
        handle.write(str(os.getpid()))
    try:
        asyncio.run(Daemon(args, apikey).run())
    finally:
        try:
            os.unlink(args.pid)
        except OSError:
            pass


if __name__ == '__main__':
    main()
