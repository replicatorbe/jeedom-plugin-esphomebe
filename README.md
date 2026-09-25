# Jeedom — plugin ESPHome (`esphomebe`)

Connexion directe aux modules ESPHome par leur API native chiffrée, sans
Home Assistant ni MQTT. Les capteurs du module sont découverts et deviennent des
commandes Jeedom ; les valeurs arrivent en temps réel.

- Démon Python (`resources/esphomebed/esphomebed.py`) basé sur
  [`aioesphomeapi`](https://github.com/esphome/aioesphomeapi), la bibliothèque
  de Home Assistant.
- Dépendances installées par Jeedom dans `resources/python_venv`.

Documentation : [docs/fr_FR/index.md](docs/fr_FR/index.md).

Licence AGPL. Ce plugin n'est pas affilié au projet ESPHome.
