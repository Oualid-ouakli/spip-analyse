# Spip - Service d'analyse de la foulee

Petit service Python qui mesure la distance parcourue sur une video de
marche et en deduit la longueur de foulee.

## Comment ca marche

La mesure est hybride : le telephone compte les pas, le serveur mesure la
distance.

1. L'utilisateur tient son telephone a la hanche, incline vers le sol, et
   marche en filmant devant lui. Pendant le film, le podometre du telephone
   (accelerometre) compte les pas.
2. L'app envoie la video, le nombre de pas comptes, la taille de pantalon
   (entrejambe) et l'inclinaison du telephone.
3. Le serveur mesure la distance parcourue par flux optique du sol : il suit
   des points du sol d'une image a l'autre (moitie basse de l'image), prend
   leur deplacement vertical median, et le convertit en metres grace a la
   geometrie hauteur / inclinaison.
4. foulee = distance totale / nombre de pas.

Le sol sert donc de reference de mouvement, et le podometre de reference de
cadence. Aucune detection de posture n'est utilisee : la camera etant portee
a la hanche, les pieds sont trop rarement dans le cadre pour etre suivis de
maniere fiable.

## Precision et calibration

Deux parametres geometriques determinent l'echelle, et le resultat y est
sensible :

- **angle_deg** (inclinaison du telephone) : le plus critique. Une erreur de
  5 deg deplace la distance d'environ 15 %.
- **FOV_VERTICAL_DEG** (champ de vision couvert par la hauteur de l'image,
  constante dans `app.py`) : fixe a 70 deg. Les videos etant en portrait, la
  hauteur de l'image correspond au grand cote du capteur, couvert par
  l'optique principale d'un telephone sur environ 65-73 deg.
- **entrejambe_cm** : effet lineaire et modere, environ 6 % pour 5 cm.

Mesure de reference sur une marche de 8 m en 10 pas (foulee reelle 0.80 m) :
le service renvoie 0.77 m avec un FOV de 70 deg, contre 0.65 m avec l'ancienne
valeur de 55 deg.

Pour gagner en precision sur tous les modeles de telephone, l'app devrait
envoyer les intrinseques reelles de la camera plutot que de s'appuyer sur une
constante (`AVCaptureDevice` sur iOS, `CameraCharacteristics` sur Android).

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

- `video` : le fichier video (marche filmee vers le sol, telephone a la hanche)
- `nb_pas` : nombre de pas comptes par le telephone (entier > 0, requis)
- `entrejambe_cm` : hauteur hanche -> sol en cm (defaut 80)
- `angle_deg` : inclinaison du telephone sous l'horizontale (defaut 40)

Reponse :

    { "foulee_m": 0.774, "distance_m": 7.74, "nb_pas": 10, "images_analysees": 313 }

En cas d'echec, la reponse contient un champ `erreur` explicite (nb_pas
manquant ou invalide, sol non exploitable, foulee hors plage plausible).

## Exemple

    curl -F "video=@marche.mp4" -F "nb_pas=10" \
         -F "entrejambe_cm=80" -F "angle_deg=40" \
         http://localhost:5000/analyser
