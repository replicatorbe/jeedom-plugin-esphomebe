<?php
/* This file is part of Jeedom.
 *
 * Jeedom is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * Jeedom is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with Jeedom. If not, see <http://www.gnu.org/licenses/>.
 */

/*
 * Point d'entrée du démon.
 *
 * Trois routes, toutes protégées par la clé API du plugin :
 *   GET  ?apikey=…&test=1          → 'OK'
 *   GET  ?apikey=…&action=config   → la configuration, en JSON
 *   POST ?apikey=…  {"events":[…]} → un lot d'événements, répond 'OK'
 *
 * L'API du plugin est en mode « localhost » (posée à l'installation) : elle ne
 * répond qu'en boucle locale, le démon étant son seul interlocuteur.
 */

require_once __DIR__ . '/../../../../core/php/core.inc.php';

/* 401 et non 200 sur refus : le démon ne dispose que de la réponse pour savoir
 * si son lot a été pris. */
/* La seule clé du plugin : jeedom::apiAccess() accepterait aussi celle de
 * n'importe quel utilisateur. apiAccess() reste appelé pour son contrôle
 * d'origine (accès du plugin limité à localhost). */
if (!is_string(init('apikey')) || !hash_equals(jeedom::getApiKey('esphomebe'), init('apikey'))
    || !jeedom::apiAccess(init('apikey'), 'esphomebe')) {
    http_response_code(401);
    echo 'Not authorized';
    die();
}

if (init('test') != '') {
    echo 'OK';
    die();
}

if (init('action') == 'config') {
    header('Content-Type: application/json');
    echo json_encode(esphomebe::getDaemonConfig());
    die();
}

$payload = json_decode(file_get_contents('php://input'), true);
if (!is_array($payload) || !isset($payload['events']) || !is_array($payload['events'])) {
    log::add('esphomebe', 'error', __('Lot d\'événements illisible.', __FILE__));
    echo 'KO';
    die();
}

/* Les modules sont résolus une fois pour tout le lot. */
$devices = array();
foreach (esphomebe::byType('esphomebe', true) as $eqLogic) {
    $devices[(int) $eqLogic->getId()] = $eqLogic;
}

foreach ($payload['events'] as $event) {
    if (!is_array($event)) {
        continue;
    }
    $id = isset($event['eq_id']) ? (int) $event['eq_id'] : 0;
    if (!isset($devices[$id])) {
        /* Module supprimé ou désactivé pendant que le lot voyageait. */
        continue;
    }
    $device = $devices[$id];

    try {
        switch (isset($event['type']) ? $event['type'] : '') {
            case 'state':
                $device->checkAndUpdateCmd((string) $event['logical_id'], $event['value']);
                break;

            case 'device':
                $device->syncDevice(
                    isset($event['info']) ? $event['info'] : array(),
                    isset($event['entities']) ? $event['entities'] : array(),
                    isset($event['unsupported']) ? $event['unsupported'] : array()
                );
                break;

            case 'status':
                $connected = (isset($event['status']) && $event['status'] == 'connected');
                $error = isset($event['error']) ? (string) $event['error'] : '';
                $device->checkAndUpdateCmd('online', $connected ? 1 : 0);
                /* Une déconnexion attendue (rechargement) ne porte pas de
                 * message : elle ne doit pas effacer la dernière erreur utile. */
                if ($connected || $error != '') {
                    $device->setCache('last_error', $error);
                }
                if ($connected) {
                    log::add('esphomebe', 'info', $device->getHumanName() . ' ' . __('connecté', __FILE__));
                } elseif ($error != '') {
                    log::add('esphomebe', 'warning', $device->getHumanName() . ' ' . __('déconnecté :', __FILE__) . ' ' . $error);
                }
                break;
        }
    } catch (Throwable $e) {
        /* Un événement en échec ne doit pas emporter le reste du lot. */
        log::add('esphomebe', 'error', $device->getHumanName() . ' : ' . $e->getMessage());
    }
}

echo 'OK';
