# =====================================================
#  Spip - Service d'analyse de la foulee (Python + Flask)
#  Methode hybride :
#   - le telephone compte les pas (accelerometre, cote app)
#   - le serveur mesure la DISTANCE parcourue par flux optique
#     du sol, puis foulee = distance / nb_pas.
#
#  Le telephone est tenu a la hanche, incline vers le sol.
#  La hauteur hanche->sol (entrejambe) + l'angle d'inclinaison
#  permettent de convertir un deplacement en pixels dans la
#  moitie basse de l'image en metres reellement parcourus.
# =====================================================

import os
import math
import tempfile

from flask import Flask, request, jsonify
from flask_cors import CORS
import cv2
import numpy as np

app = Flask(__name__)
CORS(app)

# Champ de vision couvert par la hauteur de l'image (degres).
# Les videos sont filmees en portrait : la hauteur de l'image est donc le
# GRAND cote du capteur, que l'optique principale d'un telephone couvre sur
# environ 65-73 deg. L'ancienne valeur de 55 deg correspondait au paysage
# (petit cote) et sous-estimait les distances d'environ 20 %.
# A terme l'app devrait envoyer les intrinseques reelles de la camera,
# seul moyen d'etre juste sur tous les modeles.
FOV_VERTICAL_DEG = 70.0
# Largeur d'analyse (les images sont reduites pour la vitesse/memoire)
LARGEUR_MAX = 480
# Nombre minimal de points suivis pour croire au deplacement mesure
MIN_POINTS_SUIVIS = 10
# Avance maximale plausible entre deux images (m) - au-dela c'est du bruit
AVANCE_MAX_PAR_IMAGE = 0.5
# Distance sol maximale exploitable (m) : au-dela la projection est trop etiree
DISTANCE_SOL_MAX = 6.0

PARAMS_DETECTION = dict(maxCorners=200, qualityLevel=0.01, minDistance=8, blockSize=7)
PARAMS_LK = dict(winSize=(21, 21), maxLevel=3,
                 criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))


@app.route("/", methods=["GET"])
def accueil():
    return jsonify({"message": "Service d'analyse Spip en ligne"})


@app.route("/analyser", methods=["POST"])
def analyser():
    if "video" not in request.files:
        return jsonify({"erreur": "aucune video recue"}), 400

    # nombre de pas compte par le podometre du telephone pendant le film
    brut = request.form.get("nb_pas")
    if brut is None or str(brut).strip() == "":
        return jsonify({"erreur": "nb_pas manquant (le telephone doit envoyer le nombre de pas comptes)"}), 400
    try:
        nb_pas = int(float(brut))
    except ValueError:
        return jsonify({"erreur": "nb_pas invalide (nombre entier attendu)"}), 400
    if nb_pas <= 0:
        return jsonify({"erreur": "nb_pas doit etre superieur a zero"}), 400

    # hauteur hanche -> sol en cm (entrejambe / taille de pantalon)
    entrejambe_cm = float(request.form.get("entrejambe_cm", 80))
    # inclinaison de la camera sous l'horizontale, en degres (mesuree par l'app)
    angle_deg = float(request.form.get("angle_deg", 40))
    # bornes de securite
    angle_deg = max(10.0, min(85.0, angle_deg))
    hauteur_m = max(0.4, min(1.2, entrejambe_cm / 100.0))

    fichier = request.files["video"]
    chemin = os.path.join(tempfile.gettempdir(), "marche.mp4")
    fichier.save(chemin)

    resultat = analyser_video(chemin, hauteur_m, angle_deg, nb_pas)

    try:
        os.remove(chemin)
    except OSError:
        pass

    return jsonify(resultat)


def analyser_video(chemin_video, hauteur_m, angle_deg, nb_pas):
    cap = cv2.VideoCapture(chemin_video)
    if not cap.isOpened():
        return {"erreur": "impossible de lire la video"}

    alpha = math.radians(angle_deg)  # inclinaison de l'axe camera sous l'horizontale

    distance_totale = 0.0
    nb_images = 0
    nb_paires_mesurees = 0
    precedente = None

    while True:
        ok, image = cap.read()
        if not ok:
            break
        nb_images += 1

        # reduction + niveaux de gris
        h0, w0 = image.shape[:2]
        if w0 > LARGEUR_MAX:
            image = cv2.resize(image, (LARGEUR_MAX, int(h0 * LARGEUR_MAX / w0)))
        gris = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        if precedente is not None:
            avance = avance_entre_images(precedente, gris, alpha, hauteur_m)
            if avance is not None:
                distance_totale += avance
                nb_paires_mesurees += 1

        precedente = gris

    cap.release()

    if nb_paires_mesurees < 10:
        return {"erreur": "sol non exploitable (filme un sol texture, bien eclaire, sans flou)",
                "images_analysees": nb_images,
                "paires_mesurees": nb_paires_mesurees}

    foulee = distance_totale / nb_pas

    if not (0.2 < foulee < 1.2):
        return {"erreur": "foulee hors plage plausible - verifie le nombre de pas, "
                          "la taille de pantalon et l'inclinaison du telephone",
                "foulee_calculee_m": round(foulee, 3),
                "distance_m": round(distance_totale, 2),
                "nb_pas": nb_pas,
                "images_analysees": nb_images}

    return {
        "foulee_m": round(foulee, 3),
        "distance_m": round(distance_totale, 2),
        "nb_pas": nb_pas,
        "images_analysees": nb_images,
    }


def avance_entre_images(gris_avant, gris_apres, alpha, hauteur_m):
    """Avance de la camera (m) entre deux images, mesuree sur le sol.

    Le sol occupe la moitie basse de l'image. Quand la camera avance, les
    motifs du sol descendent dans l'image. On suit des points epars, on prend
    le deplacement vertical median (robuste aux points aberrants), puis on
    convertit en metres via la geometrie hauteur/inclinaison."""
    H, W = gris_avant.shape[:2]
    f = (H / 2.0) / math.tan(math.radians(FOV_VERTICAL_DEG) / 2.0)

    # zone sol : moitie basse uniquement
    masque = np.zeros((H, W), dtype=np.uint8)
    masque[H // 2:, :] = 255

    points = cv2.goodFeaturesToTrack(gris_avant, mask=masque, **PARAMS_DETECTION)
    if points is None or len(points) < MIN_POINTS_SUIVIS:
        return None

    suivis, statut, _ = cv2.calcOpticalFlowPyrLK(gris_avant, gris_apres, points, None, **PARAMS_LK)
    if suivis is None:
        return None

    ok = statut.reshape(-1) == 1
    avant = points.reshape(-1, 2)[ok]
    apres = suivis.reshape(-1, 2)[ok]
    if len(avant) < MIN_POINTS_SUIVIS:
        return None

    dys = apres[:, 1] - avant[:, 1]

    # rejet des points aberrants autour du deplacement median
    med = float(np.median(dys))
    ecart = float(np.median(np.abs(dys - med)))
    tolerance = max(1.5, 3.0 * ecart)
    garde = np.abs(dys - med) <= tolerance
    if int(garde.sum()) < MIN_POINTS_SUIVIS:
        return None

    dy = float(np.median(dys[garde]))
    y_moyen = float(np.mean(avant[garde][:, 1]))

    # conversion en metres : distance au sol de la rangee avant, puis apres
    y_avant = distance_sol(y_moyen, H, f, alpha, hauteur_m)
    y_apres = distance_sol(y_moyen + dy, H, f, alpha, hauteur_m)
    if y_avant is None or y_apres is None:
        return None

    avance = y_avant - y_apres  # positif quand la camera avance
    if avance <= 0 or avance > AVANCE_MAX_PAR_IMAGE:
        return None
    return avance


def distance_sol(py, H, f, alpha, hauteur_m):
    """Distance au sol (m) devant la hanche, du point image situe a la rangee py.
    Un pixel a phi sous l'axe optique vise le sol sous l'angle beta = alpha + phi,
    donc a une distance avant Y = h / tan(beta)."""
    phi = math.atan((py - H / 2.0) / f)
    beta = alpha + phi
    if beta < math.radians(8):  # trop proche de l'horizon : projection instable
        return None
    Y = hauteur_m / math.tan(beta)
    if Y > DISTANCE_SOL_MAX:
        return None
    return Y


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
