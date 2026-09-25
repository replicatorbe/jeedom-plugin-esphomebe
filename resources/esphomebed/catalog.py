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
Traduction des entités ESPHome en commandes Jeedom.

Toute la connaissance des composants ESPHome est ici, et seulement ici. Pour
chaque domaine, trois choses :

- describe() : les commandes Jeedom que l'entité produit (infos d'abord, puis
  actions), sous une forme que le PHP crée telle quelle sans rien savoir
  d'ESPHome ;
- values()   : ce qu'un état reçu du module devient, commande info par
  commande info ;
- run()      : l'appel à la bibliothèque pour exécuter une commande action.

Identifiants logiques : `<domaine>::<object_id>` pour l'info principale,
`<domaine>::<object_id>::<champ>` pour les autres. Ils ne doivent jamais
changer une fois publiés : ce sont eux qui relient l'historique et les
scénarios à l'entité.
"""

import math

from aioesphomeapi import (
    AlarmControlPanelCommand,
    AlarmControlPanelEntityState,
    AlarmControlPanelInfo,
    BinarySensorInfo,
    BinarySensorState,
    ButtonInfo,
    ClimateInfo,
    ClimateMode,
    ClimatePreset,
    ClimateState,
    CoverInfo,
    CoverState,
    DateInfo,
    DateState,
    DateTimeInfo,
    DateTimeState,
    Event,
    EventInfo,
    FanInfo,
    FanState,
    LightInfo,
    LightState,
    LockCommand,
    LockEntityState,
    LockInfo,
    NumberInfo,
    NumberState,
    SelectInfo,
    SelectState,
    SensorInfo,
    SensorState,
    SirenInfo,
    SirenState,
    SwitchInfo,
    SwitchState,
    TextInfo,
    TextSensorInfo,
    TextSensorState,
    TextState,
    TimeInfo,
    TimeState,
    ValveInfo,
    ValveState,
)

# ------------------------------------------------------------ correspondances

SENSOR_GENERIC = {
    'temperature': 'TEMPERATURE',
    'humidity': 'HUMIDITY',
    'pressure': 'PRESSURE',
    'atmospheric_pressure': 'PRESSURE',
    'illuminance': 'BRIGHTNESS',
    'power': 'POWER',
    'energy': 'CONSUMPTION',
    'voltage': 'VOLTAGE',
    'current': 'CURRENT',
    'battery': 'BATTERY',
    'carbon_dioxide': 'CO2',
}

BINARY_GENERIC = {
    'door': 'OPENING',
    'garage_door': 'OPENING',
    'opening': 'OPENING',
    'window': 'OPENING_WINDOW',
    'motion': 'PRESENCE',
    'occupancy': 'PRESENCE',
    'presence': 'PRESENCE',
    'smoke': 'SMOKE',
    'moisture': 'FLOOD',
    'battery_charging': 'BATTERY_CHARGING',
}

LOCK_STATES = {0: 'inconnu', 1: 'verrouillé', 2: 'déverrouillé', 3: 'bloqué',
               4: 'verrouillage', 5: 'déverrouillage', 6: 'ouverture', 7: 'ouvert'}

OPERATIONS = {0: 'arrêt', 1: 'ouverture', 2: 'fermeture'}

CLIMATE_MODES = {0: 'off', 1: 'heat_cool', 2: 'cool', 3: 'heat', 4: 'fan_only', 5: 'dry', 6: 'auto'}
CLIMATE_MODE_LABELS = {'off': 'Arrêt', 'heat_cool': 'Chaud/froid', 'cool': 'Froid', 'heat': 'Chauffage',
                       'fan_only': 'Ventilation', 'dry': 'Déshumidification', 'auto': 'Auto'}
CLIMATE_ACTIONS = {0: 'arrêt', 2: 'refroidit', 3: 'chauffe', 4: 'au repos', 5: 'déshumidifie',
                   6: 'ventile', 7: 'dégivre'}
CLIMATE_PRESETS = {0: 'none', 1: 'home', 2: 'away', 3: 'boost', 4: 'comfort', 5: 'eco',
                   6: 'sleep', 7: 'activity'}

ALARM_STATES = {0: 'désarmée', 1: 'armée (maison)', 2: 'armée (absence)', 3: 'armée (nuit)',
                4: 'armée (vacances)', 5: 'armée (personnalisée)', 6: 'en attente', 7: 'armement',
                8: 'désarmement', 9: 'déclenchée'}
# Bits de supported_features, dans l'ordre où les commandes seront créées.
ALARM_FEATURES = [
    (1, 'arm_home', 'Armer maison', AlarmControlPanelCommand.ARM_HOME),
    (2, 'arm_away', 'Armer absence', AlarmControlPanelCommand.ARM_AWAY),
    (4, 'arm_night', 'Armer nuit', AlarmControlPanelCommand.ARM_NIGHT),
    (32, 'arm_vacation', 'Armer vacances', AlarmControlPanelCommand.ARM_VACATION),
    (16, 'arm_custom_bypass', 'Armer personnalisé', AlarmControlPanelCommand.ARM_CUSTOM_BYPASS),
    (8, 'trigger', 'Déclencher', AlarmControlPanelCommand.TRIGGER),
]

# Capacités de couleur d'une lumière (LightColorCapability).
CAP_BRIGHTNESS = 2
CAP_COLOR_TEMPERATURE = 8
CAP_RGB = 32


# ------------------------------------------------------------ outils

def clean(value):
    """Un float 32 bits ramené aux chiffres qu'il porte réellement."""
    if value is None or math.isnan(value) or math.isinf(value):
        return None
    return float('%.7g' % value)


def percent(value):
    """0..1 → 0..100, arrondi à l'unité : c'est l'échelle d'un curseur Jeedom."""
    value = clean(value)
    return None if value is None else int(round(value * 100))


def bounds(low, high, step=None):
    """
    Bornes d'un curseur, omises si le module n'en annonce pas de cohérentes :
    un curseur de 0 à 0 serait inutilisable, mieux vaut celui de Jeedom.
    """
    low, high = clean(low), clean(high)
    out = {}
    if low is not None and high is not None and high > low:
        out.update(min=low, max=high)
    step = clean(step) if step is not None else None
    if step:
        out['step'] = step
    return out


def info(field, name, subtype, **extra):
    return dict(kind='info', field=field, name=name, subtype=subtype, **extra)


def action(field, name, subtype, value=None, **extra):
    """value : le champ de l'info que l'action met à jour (retour d'état Jeedom)."""
    return dict(kind='action', field=field, name=name, subtype=subtype, value=value, **extra)


def list_value(options, labels=None):
    """Format listValue de Jeedom : valeur|libellé;valeur|libellé."""
    labels = labels or {}
    return ';'.join('%s|%s' % (o, labels.get(o, o)) for o in options)


def rgb_hex(state):
    if not (state.red or state.green or state.blue):
        return None
    return '#%02x%02x%02x' % tuple(int(round(max(0.0, min(1.0, c)) * 255))
                                   for c in (state.red, state.green, state.blue))


def light_caps(entity):
    caps = 0
    for mode in entity.supported_color_modes or []:
        caps |= int(mode)
    if entity.legacy_supports_brightness:
        caps |= CAP_BRIGHTNESS
    if entity.legacy_supports_rgb:
        caps |= CAP_RGB
    if entity.legacy_supports_color_temperature:
        caps |= CAP_COLOR_TEMPERATURE
    return caps


def climate_flags(entity):
    """Les anciens booléens et le champ feature_flags qui les remplace, fusionnés."""
    flags = int(entity.feature_flags or 0)
    return {
        'current_temperature': entity.supports_current_temperature or bool(flags & 1),
        'two_point': entity.supports_two_point_target_temperature or bool(flags & 2),
        'current_humidity': entity.supports_current_humidity or bool(flags & 8),
        'target_humidity': entity.supports_target_humidity or bool(flags & 16),
        'action': entity.supports_action or bool(flags & 32),
    }


def climate_presets(entity):
    names = [CLIMATE_PRESETS.get(int(p), str(p)) for p in entity.supported_presets or []]
    return names + list(entity.supported_custom_presets or [])


# ------------------------------------------------------------ describe

def describe(entity):
    """
    Les commandes Jeedom d'une entité, ou None si son domaine n'est pas pris en
    charge. Rend (domaine, [commandes]).
    """
    unit = getattr(entity, 'unit_of_measurement', '') or ''
    klass = getattr(entity, 'device_class', '') or ''

    if isinstance(entity, SensorInfo):
        return 'sensor', [
            info('', '', 'numeric', unit=unit, historized=1,
                 generic_type=SENSOR_GENERIC.get(klass, 'GENERIC_INFO')),
        ]

    if isinstance(entity, BinarySensorInfo):
        return 'binary_sensor', [
            info('', '', 'binary', historized=1,
                 generic_type=BINARY_GENERIC.get(klass, 'GENERIC_INFO')),
        ]

    if isinstance(entity, TextSensorInfo):
        return 'text_sensor', [info('', '', 'string')]

    if isinstance(entity, SwitchInfo):
        return 'switch', [
            info('', 'État', 'binary', historized=1, visible=0, generic_type='ENERGY_STATE'),
            action('on', 'On', 'other', value='', generic_type='ENERGY_ON'),
            action('off', 'Off', 'other', value='', generic_type='ENERGY_OFF'),
        ]

    if isinstance(entity, ButtonInfo):
        return 'button', [action('press', '', 'other')]

    if isinstance(entity, NumberInfo):
        limits = bounds(entity.min_value, entity.max_value, entity.step)
        return 'number', [
            info('', 'État', 'numeric', unit=unit, historized=1, visible=0),
            action('set', '', 'slider', value='', unit=unit, **limits),
        ]

    if isinstance(entity, SelectInfo):
        return 'select', [
            info('', 'État', 'string', visible=0),
            action('set', '', 'select', value='', list=list_value(entity.options)),
        ]

    if isinstance(entity, TextInfo):
        return 'text', [
            info('', '', 'string'),
            action('set', 'Écrire', 'message', value='', visible=0),
        ]

    if isinstance(entity, LightInfo):
        caps = light_caps(entity)
        commands = [info('', 'État', 'binary', historized=1, visible=0, generic_type='LIGHT_STATE_BOOL')]
        if caps & CAP_BRIGHTNESS:
            commands.append(info('brightness', 'Luminosité', 'numeric', unit='%', visible=0,
                                 min=0, max=100, generic_type='LIGHT_STATE'))
        if caps & CAP_RGB:
            commands.append(info('color', 'Couleur', 'string', visible=0, generic_type='LIGHT_COLOR'))
        if caps & CAP_COLOR_TEMPERATURE and entity.min_mireds and entity.max_mireds:
            commands.append(info('color_temp', 'Température de couleur', 'numeric', unit='K', visible=0,
                                 generic_type='LIGHT_COLOR_TEMP'))
        if entity.effects:
            commands.append(info('effect', 'Effet', 'string', visible=0))
        commands += [
            action('on', 'On', 'other', value='', generic_type='LIGHT_ON'),
            action('off', 'Off', 'other', value='', generic_type='LIGHT_OFF'),
        ]
        if caps & CAP_BRIGHTNESS:
            commands.append(action('set_brightness', 'Régler luminosité', 'slider', value='brightness',
                                   unit='%', min=0, max=100, step=1, generic_type='LIGHT_SLIDER'))
        if caps & CAP_RGB:
            commands.append(action('set_color', 'Régler couleur', 'color', value='color',
                                   generic_type='LIGHT_SET_COLOR'))
        if caps & CAP_COLOR_TEMPERATURE and entity.min_mireds and entity.max_mireds:
            # ESPHome parle en mireds, les humains en kelvins : 1 000 000 / mireds.
            commands.append(action('set_color_temp', 'Régler température de couleur', 'slider',
                                   value='color_temp', unit='K',
                                   min=int(round(1e6 / entity.max_mireds)),
                                   max=int(round(1e6 / entity.min_mireds)), step=50,
                                   generic_type='LIGHT_SET_COLOR_TEMP'))
        if entity.effects:
            commands.append(action('set_effect', 'Choisir effet', 'select', value='effect',
                                   list=list_value(entity.effects)))
        return 'light', commands

    if isinstance(entity, (CoverInfo, ValveInfo)):
        domain = 'cover' if isinstance(entity, CoverInfo) else 'valve'
        commands = [
            # Un volet sans position n'annonce que 0 (fermé) ou 100 (ouvert) :
            # la même commande sert aux deux.
            info('', 'Position', 'numeric', unit='%', historized=1, min=0, max=100,
                 generic_type='FLAP_STATE' if domain == 'cover' else 'GENERIC_INFO'),
            info('operation', 'Mouvement', 'string', visible=0),
            action('open', 'Ouvrir', 'other', value='',
                   generic_type='FLAP_UP' if domain == 'cover' else 'GENERIC_ACTION'),
            action('close', 'Fermer', 'other', value='',
                   generic_type='FLAP_DOWN' if domain == 'cover' else 'GENERIC_ACTION'),
        ]
        if entity.supports_stop:
            commands.append(action('stop', 'Stop', 'other',
                                   generic_type='FLAP_STOP' if domain == 'cover' else 'GENERIC_ACTION'))
        if entity.supports_position:
            commands.append(action('set_position', 'Régler position', 'slider', value='', unit='%',
                                   min=0, max=100, step=1,
                                   generic_type='FLAP_SLIDER' if domain == 'cover' else 'GENERIC_ACTION'))
        if domain == 'cover' and entity.supports_tilt:
            commands.insert(2, info('tilt', 'Inclinaison', 'numeric', unit='%', visible=0, min=0, max=100))
            commands.append(action('set_tilt', 'Régler inclinaison', 'slider', value='tilt', unit='%',
                                   min=0, max=100, step=1))
        return domain, commands

    if isinstance(entity, FanInfo):
        commands = [info('', 'État', 'binary', historized=1, visible=0, generic_type='FAN_STATE')]
        if entity.supports_speed and entity.supported_speed_count:
            commands.append(info('speed', 'Vitesse', 'numeric', visible=0,
                                 min=0, max=entity.supported_speed_count, generic_type='FAN_SPEED_STATE'))
        if entity.supports_oscillation:
            commands.append(info('oscillating', 'Oscillation', 'binary', visible=0))
        if entity.supported_preset_modes:
            commands.append(info('preset', 'Préréglage', 'string', visible=0))
        commands += [
            action('on', 'On', 'other', value='', generic_type='FAN_ON'),
            action('off', 'Off', 'other', value='', generic_type='FAN_OFF'),
        ]
        if entity.supports_speed and entity.supported_speed_count:
            commands.append(action('set_speed', 'Régler vitesse', 'slider', value='speed',
                                   min=1, max=entity.supported_speed_count, step=1,
                                   generic_type='FAN_SPEED'))
        if entity.supports_oscillation:
            commands.append(action('oscillate_on', 'Oscillation on', 'other', value='oscillating', visible=0))
            commands.append(action('oscillate_off', 'Oscillation off', 'other', value='oscillating', visible=0))
        if entity.supported_preset_modes:
            commands.append(action('set_preset', 'Choisir préréglage', 'select', value='preset',
                                   list=list_value(entity.supported_preset_modes)))
        return 'fan', commands

    if isinstance(entity, LockInfo):
        commands = [
            info('', 'Verrouillée', 'binary', historized=1, generic_type='LOCK_STATE'),
            info('status', 'État', 'string', visible=0),
            action('lock', 'Verrouiller', 'other', value='', generic_type='LOCK_CLOSE'),
            action('unlock', 'Déverrouiller', 'other', value='', generic_type='LOCK_OPEN',
                   confirm=1),
        ]
        if entity.supports_open:
            commands.append(action('open', 'Ouvrir', 'other', value='', confirm=1, visible=0))
        return 'lock', commands

    if isinstance(entity, ClimateInfo):
        flags = climate_flags(entity)
        unit = '°C'
        limits = bounds(entity.visual_min_temperature, entity.visual_max_temperature,
                        entity.visual_target_temperature_step or 0.5)
        modes = [CLIMATE_MODES.get(int(m), str(m)) for m in entity.supported_modes or []]
        presets = climate_presets(entity)
        commands = []
        if flags['current_temperature']:
            commands.append(info('current_temperature', 'Température', 'numeric', unit=unit,
                                 historized=1, generic_type='THERMOSTAT_TEMPERATURE'))
        if flags['current_humidity']:
            commands.append(info('current_humidity', 'Humidité', 'numeric', unit='%',
                                 historized=1, generic_type='HUMIDITY'))
        if flags['two_point']:
            commands.append(info('target_low', 'Consigne basse', 'numeric', unit=unit, historized=1))
            commands.append(info('target_high', 'Consigne haute', 'numeric', unit=unit, historized=1))
        else:
            commands.append(info('target', 'Consigne', 'numeric', unit=unit, historized=1,
                                 generic_type='THERMOSTAT_SETPOINT'))
        commands.append(info('mode', 'Mode', 'string', generic_type='THERMOSTAT_MODE'))
        if flags['action']:
            commands.append(info('action', 'Action', 'string', generic_type='THERMOSTAT_STATE_NAME'))
        if presets:
            commands.append(info('preset', 'Préréglage', 'string', visible=0))
        if flags['two_point']:
            commands.append(action('set_target_low', 'Régler consigne basse', 'slider', value='target_low',
                                   unit=unit, **limits))
            commands.append(action('set_target_high', 'Régler consigne haute', 'slider', value='target_high',
                                   unit=unit, **limits))
        else:
            commands.append(action('set_target', 'Régler consigne', 'slider', value='target', unit=unit,
                                   generic_type='THERMOSTAT_SET_SETPOINT', **limits))
        if modes:
            commands.append(action('set_mode', 'Choisir mode', 'select', value='mode',
                                   list=list_value(modes, CLIMATE_MODE_LABELS),
                                   generic_type='THERMOSTAT_SET_MODE'))
        if presets:
            commands.append(action('set_preset', 'Choisir préréglage', 'select', value='preset',
                                   list=list_value(presets)))
        return 'climate', commands

    if isinstance(entity, SirenInfo):
        return 'siren', [
            info('', 'État', 'binary', historized=1, visible=0, generic_type='SIREN_STATE'),
            action('on', 'On', 'other', value='', generic_type='SIREN_ON'),
            action('off', 'Off', 'other', value='', generic_type='SIREN_OFF'),
        ]

    if isinstance(entity, EventInfo):
        # Un événement répété (deux appuis courts) doit redéclencher les
        # scénarios même si le type ne change pas.
        return 'event', [info('', '', 'string', repeat=1)]

    if isinstance(entity, AlarmControlPanelInfo):
        code = 'message' if entity.requires_code or entity.requires_code_to_arm else 'other'
        commands = [
            info('', 'État', 'string', historized=1, generic_type='ALARM_MODE'),
            action('disarm', 'Désarmer', 'message' if entity.requires_code else 'other',
                   value='', generic_type='ALARM_RELEASED'),
        ]
        for bit, field, name, _command in ALARM_FEATURES:
            if entity.supported_features & bit:
                commands.append(action(field, name, 'other' if field == 'trigger' else code, value=''))
        return 'alarm_control_panel', commands

    if isinstance(entity, (DateInfo, TimeInfo, DateTimeInfo)):
        domain = {DateInfo: 'date', TimeInfo: 'time', DateTimeInfo: 'datetime'}[type(entity)]
        return domain, [info('', '', 'string')]

    return None


# ------------------------------------------------------------ values

def values(domain, entity, state):
    """{champ: valeur} pour un état reçu. Un champ absent n'est pas mis à jour."""
    if getattr(state, 'missing_state', False):
        return {}

    if isinstance(state, SensorState):
        value = clean(state.state)
        return {} if value is None else {'': value}

    if isinstance(state, (BinarySensorState, SwitchState, SirenState)):
        return {'': 1 if state.state else 0}

    if isinstance(state, (TextSensorState, TextState, SelectState)):
        return {'': state.state}

    if isinstance(state, NumberState):
        value = clean(state.state)
        return {} if value is None else {'': value}

    if isinstance(state, LightState):
        out = {'': 1 if state.state else 0}
        caps = light_caps(entity)
        if caps & CAP_BRIGHTNESS:
            out['brightness'] = percent(state.brightness) if state.state else 0
        if caps & CAP_RGB:
            color = rgb_hex(state)
            if color is not None:
                out['color'] = color
        if caps & CAP_COLOR_TEMPERATURE and state.color_temperature:
            out['color_temp'] = int(round(1e6 / state.color_temperature))
        if entity.effects:
            out['effect'] = state.effect
        return out

    if isinstance(state, (CoverState, ValveState)):
        out = {'': percent(state.position),
               'operation': OPERATIONS.get(int(state.current_operation), '')}
        if isinstance(state, CoverState) and entity.supports_tilt:
            out['tilt'] = percent(state.tilt)
        return out

    if isinstance(state, FanState):
        out = {'': 1 if state.state else 0}
        if entity.supports_speed and entity.supported_speed_count:
            out['speed'] = int(state.speed_level) if state.state else 0
        if entity.supports_oscillation:
            out['oscillating'] = 1 if state.oscillating else 0
        if entity.supported_preset_modes:
            out['preset'] = state.preset_mode
        return out

    if isinstance(state, LockEntityState):
        code = int(state.state)
        out = {'status': LOCK_STATES.get(code, str(code))}
        if code in (1, 2, 7):   # seuls états stables : le reste ne dit pas si c'est fermé
            out[''] = 1 if code == 1 else 0
        return out

    if isinstance(state, ClimateState):
        flags = climate_flags(entity)
        out = {'mode': CLIMATE_MODES.get(int(state.mode), str(state.mode))}
        if flags['current_temperature']:
            out['current_temperature'] = clean(state.current_temperature)
        if flags['current_humidity']:
            out['current_humidity'] = clean(state.current_humidity)
        if flags['two_point']:
            out['target_low'] = clean(state.target_temperature_low)
            out['target_high'] = clean(state.target_temperature_high)
        else:
            out['target'] = clean(state.target_temperature)
        if flags['action']:
            out['action'] = CLIMATE_ACTIONS.get(int(state.action), str(state.action))
        if climate_presets(entity):
            out['preset'] = state.custom_preset or CLIMATE_PRESETS.get(int(state.preset), '')
        return {k: v for k, v in out.items() if v is not None}

    if isinstance(state, Event):
        return {'': state.event_type}

    if isinstance(state, AlarmControlPanelEntityState):
        return {'': ALARM_STATES.get(int(state.state), str(state.state))}

    if isinstance(state, DateState):
        return {'': '%04d-%02d-%02d' % (state.year, state.month, state.day)}
    if isinstance(state, TimeState):
        return {'': '%02d:%02d:%02d' % (state.hour, state.minute, state.second)}
    if isinstance(state, DateTimeState):
        import datetime
        return {'': datetime.datetime.fromtimestamp(state.epoch_seconds).strftime('%Y-%m-%d %H:%M:%S')}

    return {}


# ------------------------------------------------------------ run

def _number(value, what):
    try:
        return float(str(value).replace(',', '.'))
    except (TypeError, ValueError):
        raise RuntimeError('valeur de %s illisible : %r' % (what, value))


def _hex_to_rgb(value):
    text = str(value or '').strip().lstrip('#')
    if len(text) != 6:
        raise RuntimeError('couleur illisible : %r' % value)
    return tuple(int(text[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def run(client, domain, entity, act, value):
    """Exécute une action. Lève RuntimeError si elle n'a pas de sens pour l'entité."""
    key = entity.key
    dev = entity.device_id

    if domain in ('switch', 'siren') and act in ('on', 'off'):
        call = client.switch_command if domain == 'switch' else client.siren_command
        return call(key, act == 'on', device_id=dev)

    if domain == 'button' and act == 'press':
        return client.button_command(key, device_id=dev)

    if domain == 'number' and act == 'set':
        return client.number_command(key, _number(value, 'consigne'), device_id=dev)

    if domain == 'select' and act == 'set':
        if value not in entity.options:
            raise RuntimeError('option inconnue : %r' % value)
        return client.select_command(key, value, device_id=dev)

    if domain == 'text' and act == 'set':
        return client.text_command(key, str(value or ''), device_id=dev)

    if domain == 'light':
        if act == 'on':
            return client.light_command(key, state=True, device_id=dev)
        if act == 'off':
            return client.light_command(key, state=False, device_id=dev)
        if act == 'set_brightness':
            level = max(0.0, min(100.0, _number(value, 'luminosité'))) / 100.0
            if level == 0:
                return client.light_command(key, state=False, device_id=dev)
            return client.light_command(key, state=True, brightness=level, device_id=dev)
        if act == 'set_color':
            return client.light_command(key, state=True, rgb=_hex_to_rgb(value), device_id=dev)
        if act == 'set_color_temp':
            kelvin = _number(value, 'température de couleur')
            if kelvin <= 0:
                raise RuntimeError('température de couleur nulle')
            return client.light_command(key, state=True, color_temperature=1e6 / kelvin, device_id=dev)
        if act == 'set_effect':
            return client.light_command(key, state=True, effect=str(value), device_id=dev)

    if domain in ('cover', 'valve'):
        call = client.cover_command if domain == 'cover' else client.valve_command
        if act == 'open':
            return call(key, position=1.0, device_id=dev)
        if act == 'close':
            return call(key, position=0.0, device_id=dev)
        if act == 'stop':
            return call(key, stop=True, device_id=dev)
        if act == 'set_position':
            return call(key, position=max(0.0, min(100.0, _number(value, 'position'))) / 100.0, device_id=dev)
        if act == 'set_tilt' and domain == 'cover':
            return call(key, tilt=max(0.0, min(100.0, _number(value, 'inclinaison'))) / 100.0, device_id=dev)

    if domain == 'fan':
        if act in ('on', 'off'):
            return client.fan_command(key, state=(act == 'on'), device_id=dev)
        if act == 'set_speed':
            level = int(round(_number(value, 'vitesse')))
            if level <= 0:
                return client.fan_command(key, state=False, device_id=dev)
            return client.fan_command(key, state=True, speed_level=level, device_id=dev)
        if act in ('oscillate_on', 'oscillate_off'):
            return client.fan_command(key, oscillating=(act == 'oscillate_on'), device_id=dev)
        if act == 'set_preset':
            return client.fan_command(key, preset_mode=str(value), device_id=dev)

    if domain == 'lock':
        command = {'lock': LockCommand.LOCK, 'unlock': LockCommand.UNLOCK, 'open': LockCommand.OPEN}.get(act)
        if command is not None:
            return client.lock_command(key, command, device_id=dev)

    if domain == 'climate':
        if act == 'set_target':
            return client.climate_command(key, target_temperature=_number(value, 'consigne'), device_id=dev)
        if act == 'set_target_low':
            return client.climate_command(key, target_temperature_low=_number(value, 'consigne'), device_id=dev)
        if act == 'set_target_high':
            return client.climate_command(key, target_temperature_high=_number(value, 'consigne'), device_id=dev)
        if act == 'set_mode':
            modes = {v: k for k, v in CLIMATE_MODES.items()}
            if value not in modes:
                raise RuntimeError('mode inconnu : %r' % value)
            return client.climate_command(key, mode=ClimateMode(modes[value]), device_id=dev)
        if act == 'set_preset':
            presets = {v: k for k, v in CLIMATE_PRESETS.items()}
            if value in presets:
                return client.climate_command(key, preset=ClimatePreset(presets[value]), device_id=dev)
            return client.climate_command(key, custom_preset=str(value), device_id=dev)

    if domain == 'alarm_control_panel':
        commands = {field: command for _bit, field, _name, command in ALARM_FEATURES}
        commands['disarm'] = AlarmControlPanelCommand.DISARM
        if act in commands:
            code = str(value) if value not in (None, '') else None
            return client.alarm_control_panel_command(key, commands[act], code, device_id=dev)

    raise RuntimeError('action %s impossible sur une entité %s' % (act, domain))
