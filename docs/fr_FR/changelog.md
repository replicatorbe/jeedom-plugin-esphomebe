# Changelog

## 0.2 — 2026-10-18

- Un refus HTTP 403 (page d'Apache en incident) n'abandonne plus le lot de
  valeurs : il est conservé et renvoyé, comme un 502, 503 ou 504. Le plugin
  répond 401 pour une mauvaise clé, qui reste un refus définitif.
- L'attente entre deux essais d'envoi double à chaque échec (10 s, puis
  jusqu'à 60 s au plus).

## 0.1 — 2026-09-25

- Première version : connexion par l'API native chiffrée et découverte des
  entités.
- Composants pris en charge : capteurs, capteurs binaires et textes,
  interrupteurs, boutons, nombres, listes, textes modifiables, lumières
  (luminosité, couleur, température, effets), volets, vannes, ventilateurs,
  serrures, thermostats, sirènes, événements, centrales d'alarme, dates et
  heures.
