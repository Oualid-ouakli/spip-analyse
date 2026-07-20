# Spip - Service d'analyse de la foulee

Petit service Python qui analyse une video de marche et calcule
la longueur de foulee, avec MediaPipe (detection de posture).

## Comment ca marche

1. L'app envoie une video de la personne qui marche (filmee de profil)
   + la taille de la personne en cm.
2. Le service detecte la posture image par image.
3. Il utilise la hauteur de la hanche par rapport au sol comme
   reference d'echelle (hauteur hanche reelle ~ 0.52 * taille),
   pour convertir les pixels en metres.
4. Il suit les chevilles, detecte chaque pas, mesure sa longueur,
   et renvoie la foulee moyenne.

## Installation (une seule fois)

Dans ce dossier :

    pip install -r requirements.txt

(Si pip ne marche pas, essaie : py -m pip install -r requirements.txt)

## Demarrer le service

    python app.py

(ou : py app.py)

Tu verras Flask demarrer sur http://localhost:5000

## Tester rapidement

Ouvre http://localhost:5000 dans le navigateur :
tu dois voir {"message": "Service d'analyse Spip en ligne"}

## La route principale

POST /analyser
- champ "video" : le fichier video
- champ "taille_cm" : la taille de la personne en cm

Reponse : { "foulee_m": 0.72, "nb_pas_detectes": 6, "echelle_m_par_px": ... }
