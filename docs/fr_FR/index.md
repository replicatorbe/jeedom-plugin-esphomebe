# Plugin ESPHome

Connexion directe aux modules [ESPHome](https://esphome.io) par leur API
native, sans Home Assistant, sans MQTT et sans reflasher les modules.

Le plugin parle au module exactement comme Home Assistant le fait : même port
(6053), même chiffrement, même bibliothèque (`aioesphomeapi`). Un module déjà
suivi par Home Assistant peut donc l'être aussi par Jeedom en même temps, et le
restera le jour où Home Assistant disparaît.

## Ce qui remonte

À chaque connexion, le module décrit ses entités et le plugin crée les
commandes qui manquent :

| Entité ESPHome        | Infos                                              | Actions                                                    |
|-----------------------|----------------------------------------------------|------------------------------------------------------------|
| `sensor`              | valeur numérique, unité du YAML, historisée        | —                                                          |
| `binary_sensor`       | valeur binaire, historisée                         | —                                                          |
| `text_sensor`         | texte                                              | —                                                          |
| `switch`              | état                                               | On, Off                                                    |
| `button`              | —                                                  | appui                                                      |
| `number`              | valeur                                             | curseur (bornes et pas du YAML)                            |
| `select`              | option courante                                    | liste des options                                          |
| `text`                | texte                                              | écrire (message)                                           |
| `light`               | état, luminosité, couleur, température, effet      | On, Off, luminosité, couleur, température (K), effet       |
| `cover`               | position (%), mouvement, inclinaison               | Ouvrir, Fermer, Stop, position, inclinaison                |
| `valve`               | position (%), mouvement                            | Ouvrir, Fermer, Stop, position                             |
| `fan`                 | état, vitesse, oscillation, préréglage             | On, Off, vitesse, oscillation, préréglage                  |
| `lock`                | verrouillée (binaire), état détaillé               | Verrouiller, Déverrouiller (avec confirmation), Ouvrir     |
| `climate`             | température, humidité, consigne(s), mode, action   | consigne(s), mode, préréglage                              |
| `siren`               | état                                               | On, Off                                                    |
| `event`               | dernier événement (répété à chaque occurrence)     | —                                                          |
| `alarm_control_panel` | état                                               | Désarmer, Armer (maison, absence, nuit…), code en message  |
| `date`, `time`, `datetime` | valeur en texte                               | —                                                          |

Seules les commandes qui ont un sens pour l'entité sont créées : une lumière
sans couleur n'a pas de commande couleur, un volet sans position n'a pas de
curseur. Les types génériques Jeedom (lumière, volet, thermostat, serrure…)
sont posés, pour l'application mobile et les plugins qui s'en servent.

Non pris en charge : caméras, lecteurs multimédia, mises à jour de firmware,
proxy Bluetooth et assistant vocal. Ils sont listés sur la page de
l'équipement sous « Non pris en charge ».

Les valeurs sont **poussées par le module** dès qu'elles changent : il n'y a
aucune interrogation périodique à régler.

Les entités de diagnostic (signal Wi-Fi, durée de fonctionnement…) et celles
que le YAML désactive par défaut sont créées masquées. Les autres types
(lumières, volets, climatisation…) sont listés sur la page de l'équipement
sous « Non pris en charge ».

Le plugin crée aussi deux commandes propres : **Connecté** (1 tant que la
connexion au module est établie) et **Reconnecter**.

Une commande n'est jamais réécrite après sa création : son nom, sa visibilité
et son historisation vous appartiennent.

## Installation

1. Installez les dépendances depuis la page de configuration du plugin. Elles
   sont placées dans un environnement Python propre au plugin, sans toucher au
   système.
2. Ajoutez un module : son **adresse IP** et sa **clé API**.
3. Enregistrez : le démon démarre (ou se recharge) et les commandes
   apparaissent quelques secondes plus tard.

### Où trouver la clé API

C'est la clé de chiffrement du YAML du module :

```yaml
api:
  encryption:
    key: "Q2VjaSBuJ2VzdCBwYXMgdW5lIHZyYWllIGNsw6kgIQ=="
```

On la retrouve aussi dans le tableau de bord ESPHome (« Edit » du module), ou
dans Home Assistant : *Paramètres → Appareils et services → ESPHome →
(module) → Reconfigurer*. Un module sans chiffrement laisse le champ vide.

## Dépannage

- **« clé API refusée par le module »** : la clé ne correspond pas à celle du
  firmware. Vérifiez-la caractère par caractère, `=` final compris.
- **Le module ne se connecte pas** : le bouton « État des connexions » de la
  page du plugin dit, module par module, ce que voit le démon. Le journal
  `esphomebed` donne le détail ; passez le plugin en niveau *debug* pour voir
  aussi les messages de la bibliothèque.
- **Un capteur ajouté au YAML n'apparaît pas** : il apparaît à la connexion
  suivante, donc après la mise à jour du module. La commande « Reconnecter »
  force cette relecture.
- **Une commande supprimée revient** : le module redécrit ses entités à chaque
  connexion, et le plugin recrée ce qui manque. Pour s'en débarrasser, masquez-
  la plutôt que de la supprimer.
- **Renommer une entité dans le YAML** crée une nouvelle commande : son
  identifiant découle du nom. L'ancienne reste, avec son historique, et ne
  reçoit plus rien ; supprimez-la une fois les scénarios repointés.
- **« Connecté » passe à 0 sans raison apparente** : le démon s'est arrêté. Le
  plugin le détecte en cinq minutes au plus et le coeur de Jeedom le relance.
