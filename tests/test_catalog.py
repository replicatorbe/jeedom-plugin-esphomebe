"""
Contrôle du catalogue ESPHome → Jeedom, sans module réel.

Les entités sont construites avec les vraies classes d'aioesphomeapi et les
ordres partent vers un faux client qui les enregistre. Lancer avec le Python
qui porte aioesphomeapi :

    resources/python_venv/bin/python3 tests/test_catalog.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'resources', 'esphomebed'))

import catalog  # noqa: E402
from aioesphomeapi import model as m  # noqa: E402

FAILURES = []


def check(condition, message):
    if not condition:
        FAILURES.append(message)


class FakeClient:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
        return record


def base(cls, **kw):
    return cls(object_id=kw.pop('object_id', 'test'), key=kw.pop('key', 42), name=kw.pop('name', 'Test'), **kw)


def ids(commands, kind=None):
    return [c['field'] for c in commands if kind is None or c['kind'] == kind]


def structural(domain, commands):
    """Invariants communs : champs uniques, infos avant actions, retours d'état existants."""
    fields = [(c['kind'], c['field']) for c in commands]
    check(len(fields) == len(set(fields)), '%s : champs en double %s' % (domain, fields))
    kinds = [c['kind'] for c in commands]
    check(kinds == sorted(kinds, key=lambda k: k != 'info'), '%s : une action précède une info' % domain)
    infos = set(ids(commands, 'info'))
    for c in commands:
        if c['kind'] == 'action' and c.get('value') is not None:
            check(c['value'] in infos, '%s : %s renvoie vers une info absente (%r)' % (domain, c['field'], c['value']))
        check(c['subtype'] in ('numeric', 'binary', 'string', 'other', 'slider', 'select', 'color', 'message'),
              '%s : sous-type inconnu %s' % (domain, c['subtype']))


def run(domain, entity, act, value=None):
    client = FakeClient()
    catalog.run(client, domain, entity, act, value)
    return client.calls[-1]


# ------------------------------------------------------------ capteurs

e = base(m.SensorInfo, unit_of_measurement='°C', device_class='temperature', accuracy_decimals=0)
domain, cmds = catalog.describe(e)
structural(domain, cmds)
check(cmds[0]['generic_type'] == 'TEMPERATURE', 'sensor : type générique')
check(catalog.values(domain, e, m.SensorState(key=42, state=22.600000381469727)) == {'': 22.6},
      'sensor : 22.6 attendu (pas d\'arrondi à accuracy_decimals)')
check(catalog.values(domain, e, m.SensorState(key=42, state=float('nan'))) == {}, 'sensor : NaN ignoré')
check(catalog.values(domain, e, m.SensorState(key=42, state=1.0, missing_state=True)) == {}, 'sensor : missing_state')

e = base(m.BinarySensorInfo, device_class='door')
domain, cmds = catalog.describe(e)
check(cmds[0]['generic_type'] == 'OPENING', 'binary_sensor : type générique')
check(catalog.values(domain, e, m.BinarySensorState(key=42, state=True)) == {'': 1}, 'binary_sensor : valeur')

e = base(m.TextSensorInfo)
domain, cmds = catalog.describe(e)
check(catalog.values(domain, e, m.TextSensorState(key=42, state='ok')) == {'': 'ok'}, 'text_sensor')

# ------------------------------------------------------------ interrupteur, bouton, sirène

for cls, st, dom, method in ((m.SwitchInfo, m.SwitchState, 'switch', 'switch_command'),
                              (m.SirenInfo, m.SirenState, 'siren', 'siren_command')):
    e = base(cls)
    domain, cmds = catalog.describe(e)
    structural(domain, cmds)
    check(domain == dom, dom + ' : domaine')
    check(catalog.values(domain, e, st(key=42, state=True)) == {'': 1}, dom + ' : état')
    name, args, kw = run(domain, e, 'on')
    check(name == method and args == (42, True), dom + ' : on → %r' % ((name, args),))

e = base(m.ButtonInfo)
domain, cmds = catalog.describe(e)
check(ids(cmds, 'action') == ['press'], 'button : action press')
check(run(domain, e, 'press')[0] == 'button_command', 'button : appel')

# ------------------------------------------------------------ number, select, text

e = base(m.NumberInfo, min_value=5, max_value=30, step=0.5, unit_of_measurement='°C')
domain, cmds = catalog.describe(e)
structural(domain, cmds)
slider = [c for c in cmds if c['subtype'] == 'slider'][0]
check((slider['min'], slider['max'], slider['step']) == (5, 30, 0.5), 'number : bornes du curseur')
name, args, kw = run(domain, e, 'set', '21,5')
check(name == 'number_command' and args == (42, 21.5), 'number : virgule décimale acceptée → %r' % (args,))

e = base(m.SelectInfo, options=['Eco', 'Confort'])
domain, cmds = catalog.describe(e)
structural(domain, cmds)
check([c for c in cmds if c['subtype'] == 'select'][0]['list'] == 'Eco|Eco;Confort|Confort', 'select : listValue')
check(run(domain, e, 'set', 'Eco')[1] == (42, 'Eco'), 'select : appel')
try:
    run(domain, e, 'set', 'Inconnu')
    check(False, 'select : une option inconnue doit être refusée')
except RuntimeError:
    pass

e = base(m.TextInfo)
domain, cmds = catalog.describe(e)
structural(domain, cmds)
check(run(domain, e, 'set', 'bonjour')[1] == (42, 'bonjour'), 'text : appel')

# ------------------------------------------------------------ lumière

e = base(m.LightInfo, supported_color_modes=[35, 11], min_mireds=153, max_mireds=500, effects=['None', 'Rainbow'])
domain, cmds = catalog.describe(e)
structural(domain, cmds)
check(set(ids(cmds, 'info')) == {'', 'brightness', 'color', 'color_temp', 'effect'}, 'light : infos %s' % ids(cmds, 'info'))
check(set(ids(cmds, 'action')) == {'on', 'off', 'set_brightness', 'set_color', 'set_color_temp', 'set_effect'},
      'light : actions %s' % ids(cmds, 'action'))
temp = [c for c in cmds if c['field'] == 'set_color_temp'][0]
check((temp['min'], temp['max']) == (2000, 6536), 'light : kelvins %r' % ((temp['min'], temp['max']),))
v = catalog.values(domain, e, m.LightState(key=42, state=True, brightness=0.5, red=1.0, green=0.5, blue=0.0,
                                           color_temperature=250.0, effect='Rainbow'))
check(v == {'': 1, 'brightness': 50, 'color': '#ff8000', 'color_temp': 4000, 'effect': 'Rainbow'}, 'light : valeurs %r' % v)
v = catalog.values(domain, e, m.LightState(key=42, state=False, brightness=0.5))
check(v.get('brightness') == 0, 'light : éteinte → luminosité 0')
name, args, kw = run(domain, e, 'set_brightness', 30)
check(kw.get('brightness') == 0.3 and kw.get('state') is True, 'light : luminosité %r' % kw)
name, args, kw = run(domain, e, 'set_brightness', 0)
check(kw.get('state') is False, 'light : luminosité 0 éteint')
name, args, kw = run(domain, e, 'set_color', '#ff8000')
check(kw.get('rgb') == (1.0, 128 / 255, 0.0), 'light : couleur %r' % (kw.get('rgb'),))
name, args, kw = run(domain, e, 'set_color_temp', 4000)
check(kw.get('color_temperature') == 250.0, 'light : mireds %r' % kw.get('color_temperature'))

e = base(m.LightInfo, supported_color_modes=[1])
domain, cmds = catalog.describe(e)
check(set(ids(cmds)) == {'', 'on', 'off'}, 'light on/off seule : %s' % ids(cmds))

# ------------------------------------------------------------ volet, vanne

e = base(m.CoverInfo, supports_position=True, supports_stop=True, supports_tilt=True, device_class='shutter')
domain, cmds = catalog.describe(e)
structural(domain, cmds)
check(set(ids(cmds, 'action')) == {'open', 'close', 'stop', 'set_position', 'set_tilt'}, 'cover : actions %s' % ids(cmds, 'action'))
v = catalog.values(domain, e, m.CoverState(key=42, position=0.25, tilt=1.0, current_operation=m.CoverOperation.IS_OPENING))
check(v == {'': 25, 'operation': 'ouverture', 'tilt': 100}, 'cover : valeurs %r' % v)
check(run(domain, e, 'set_position', 40)[2].get('position') == 0.4, 'cover : position')
check(run(domain, e, 'stop')[2].get('stop') is True, 'cover : stop')

e = base(m.CoverInfo)
domain, cmds = catalog.describe(e)
check(set(ids(cmds, 'action')) == {'open', 'close'}, 'cover simple : %s' % ids(cmds, 'action'))

e = base(m.ValveInfo, supports_position=True)
domain, cmds = catalog.describe(e)
structural(domain, cmds)
check(domain == 'valve' and run(domain, e, 'open')[0] == 'valve_command', 'valve')

# ------------------------------------------------------------ ventilateur

e = base(m.FanInfo, supports_speed=True, supported_speed_count=3, supports_oscillation=True,
         supported_preset_modes=['Nuit'])
domain, cmds = catalog.describe(e)
structural(domain, cmds)
v = catalog.values(domain, e, m.FanState(key=42, state=True, speed_level=2, oscillating=True, preset_mode='Nuit'))
check(v == {'': 1, 'speed': 2, 'oscillating': 1, 'preset': 'Nuit'}, 'fan : valeurs %r' % v)
check(run(domain, e, 'set_speed', 3)[2] == {'state': True, 'speed_level': 3, 'device_id': 0}, 'fan : vitesse')

# ------------------------------------------------------------ serrure

e = base(m.LockInfo, supports_open=True)
domain, cmds = catalog.describe(e)
structural(domain, cmds)
check(catalog.values(domain, e, m.LockEntityState(key=42, state=m.LockState.LOCKED)) == {'status': 'verrouillé', '': 1},
      'lock : verrouillée')
check('' not in catalog.values(domain, e, m.LockEntityState(key=42, state=m.LockState.JAMMED)),
      'lock : bloquée ne dit pas si c\'est fermé')
check(run(domain, e, 'unlock')[1] == (42, m.LockCommand.UNLOCK), 'lock : déverrouiller')
check([c for c in cmds if c['field'] == 'unlock'][0].get('confirm') == 1, 'lock : confirmation au déverrouillage')

# ------------------------------------------------------------ thermostat

e = base(m.ClimateInfo, supports_current_temperature=True, supports_action=True,
         supported_modes=[m.ClimateMode.OFF, m.ClimateMode.HEAT], visual_min_temperature=7,
         visual_max_temperature=30, visual_target_temperature_step=0.5,
         supported_presets=[m.ClimatePreset.ECO], supported_custom_presets=['Vacances'])
domain, cmds = catalog.describe(e)
structural(domain, cmds)
mode = [c for c in cmds if c['field'] == 'set_mode'][0]
check(mode['list'] == 'off|Arrêt;heat|Chauffage', 'climate : liste des modes %r' % mode['list'])
v = catalog.values(domain, e, m.ClimateState(key=42, mode=m.ClimateMode.HEAT, action=m.ClimateAction.HEATING,
                                             current_temperature=19.5, target_temperature=21.0,
                                             preset=m.ClimatePreset.ECO))
check(v == {'mode': 'heat', 'current_temperature': 19.5, 'target': 21.0, 'action': 'chauffe', 'preset': 'eco'},
      'climate : valeurs %r' % v)
check(run(domain, e, 'set_target', '20.5')[2].get('target_temperature') == 20.5, 'climate : consigne')
check(run(domain, e, 'set_mode', 'heat')[2].get('mode') == m.ClimateMode.HEAT, 'climate : mode')
check(run(domain, e, 'set_preset', 'eco')[2].get('preset') == m.ClimatePreset.ECO, 'climate : préréglage')
check(run(domain, e, 'set_preset', 'Vacances')[2].get('custom_preset') == 'Vacances', 'climate : préréglage perso')

e = base(m.ClimateInfo, feature_flags=2 | 1)
domain, cmds = catalog.describe(e)
structural(domain, cmds)
check({'target_low', 'target_high'} <= set(ids(cmds, 'info')) and 'target' not in ids(cmds),
      'climate deux consignes via feature_flags : %s' % ids(cmds))

e = base(m.ClimateInfo, supported_modes=[0])
domain, cmds = catalog.describe(e)
slider = [c for c in cmds if c['field'] == 'set_target'][0]
check('min' not in slider and 'max' not in slider, 'climate sans bornes : pas de curseur 0..0 %r' % slider)

# ------------------------------------------------------------ événement, alarme, dates

e = base(m.EventInfo, event_types=['single', 'double'])
domain, cmds = catalog.describe(e)
check(cmds[0].get('repeat') == 1, 'event : répétition')
check(catalog.values(domain, e, m.Event(key=42, event_type='double')) == {'': 'double'}, 'event : valeur')

e = base(m.AlarmControlPanelInfo, supported_features=1 | 2 | 8, requires_code=True)
domain, cmds = catalog.describe(e)
structural(domain, cmds)
check(set(ids(cmds, 'action')) == {'disarm', 'arm_home', 'arm_away', 'trigger'}, 'alarm : actions %s' % ids(cmds, 'action'))
check([c for c in cmds if c['field'] == 'disarm'][0]['subtype'] == 'message', 'alarm : code demandé')
name, args, kw = run(domain, e, 'disarm', '1234')
check(args == (42, m.AlarmControlPanelCommand.DISARM, '1234'), 'alarm : désarmer %r' % (args,))
check(catalog.values(domain, e, m.AlarmControlPanelEntityState(key=42, state=m.AlarmControlPanelState.TRIGGERED))
      == {'': 'déclenchée'}, 'alarm : état')

e = base(m.DateInfo)
domain, cmds = catalog.describe(e)
check(catalog.values(domain, e, m.DateState(key=42, year=2026, month=9, day=5)) == {'': '2026-09-05'}, 'date')

# ------------------------------------------------------------ non pris en charge

check(catalog.describe(base(m.CameraInfo)) is None, 'camera : non prise en charge')

try:
    run('switch', base(m.SwitchInfo), 'press')
    check(False, 'une action absurde doit être refusée')
except RuntimeError:
    pass

# ------------------------------------------------------------ noms

# Deux commandes d'une même entité ne doivent jamais porter le même nom : le
# PHP devrait alors suffixer l'identifiant technique pour contourner l'unicité SQL.
for e in [base(m.SwitchInfo), base(m.ButtonInfo), base(m.NumberInfo, min_value=0, max_value=1, step=1),
          base(m.SelectInfo, options=['a']), base(m.TextInfo),
          base(m.LightInfo, supported_color_modes=[35, 11], min_mireds=153, max_mireds=500, effects=['e']),
          base(m.CoverInfo, supports_position=True, supports_stop=True, supports_tilt=True),
          base(m.ValveInfo, supports_position=True, supports_stop=True),
          base(m.FanInfo, supports_speed=True, supported_speed_count=3, supports_oscillation=True,
               supported_preset_modes=['p']),
          base(m.LockInfo, supports_open=True),
          base(m.ClimateInfo, feature_flags=63, supported_modes=[0, 3], supported_presets=[1]),
          base(m.ClimateInfo, supports_current_temperature=True, supported_modes=[0]),
          base(m.SirenInfo), base(m.EventInfo),
          base(m.AlarmControlPanelInfo, supported_features=63, requires_code=True)]:
    domain, cmds = catalog.describe(e)
    names = [c['name'] for c in cmds]
    check(len(names) == len(set(names)), '%s : noms en double %s' % (domain, names))

if FAILURES:
    print('%d échec(s) :' % len(FAILURES))
    for failure in FAILURES:
        print('  - ' + failure)
    sys.exit(1)
print('catalogue : tous les contrôles passent')
