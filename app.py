# =====================================================
#  Spip - Service d'analyse de la foulee (Python + Flask)
#  Recoit une video de marche, detecte la posture avec
#  MediaPipe, et calcule la longueur de foulee en metres.
# =====================================================

import os
import tempfile
import math

from flask import Flask, request, jsonify
from flask_cors import CORS
import cv2
import mediapipe as mp

app = Flask(__name__)
CORS(app)

mp_pose = mp.solutions.pose

# Ratio anatomique : hauteur de la hanche par rapport au sol ~ 0.52 * taille.
# On l'utilise pour convertir les pixels en metres (reference d'echelle).
RATIO_HANCHE = 0.52


@app.route("/", methods=["GET"])
def accueil():
    return jsonify({"message": "Service d'analyse Spip en ligne"})


@app.route("/analyser", methods=["POST"])
def analyser():
    # 1) Recuperer la video et la taille de la personne
    if "video" not in request.files:
        return jsonify({"erreur": "aucune video recue"}), 400

    taille_cm = float(request.form.get("taille_cm", 170))  # defaut 170 cm
    hauteur_hanche_reelle_m = (taille_cm / 100.0) * RATIO_HANCHE

    fichier = request.files["video"]
    chemin = os.path.join(tempfile.gettempdir(), "marche.mp4")
    fichier.save(chemin)

    # 2) Analyser la video image par image
    resultat = analyser_video(chemin, hauteur_hanche_reelle_m)

    try:
        os.remove(chemin)
    except OSError:
        pass

    return jsonify(resultat)


def analyser_video(chemin_video, hauteur_hanche_reelle_m):
    cap = cv2.VideoCapture(chemin_video)
    if not cap.isOpened():
        return {"erreur": "impossible de lire la video"}

    positions_cheville_g = []  # (frame, x_px, y_px)
    positions_cheville_d = []
    echelles = []              # metres par pixel, estime a chaque image

    frame_idx = 0
    with mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5) as pose:
        while True:
            ok, image = cap.read()
            if not ok:
                break

            h, w = image.shape[:2]
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            res = pose.process(image_rgb)

            if res.pose_landmarks:
                lm = res.pose_landmarks.landmark

                # points utiles (indices MediaPipe)
                hanche_g = lm[mp_pose.PoseLandmark.LEFT_HIP]
                hanche_d = lm[mp_pose.PoseLandmark.RIGHT_HIP]
                cheville_g = lm[mp_pose.PoseLandmark.LEFT_ANKLE]
                cheville_d = lm[mp_pose.PoseLandmark.RIGHT_ANKLE]

                # position moyenne de la hanche et des chevilles (en pixels)
                hanche_y = ((hanche_g.y + hanche_d.y) / 2) * h
                cheville_y = ((cheville_g.y + cheville_d.y) / 2) * h

                # hauteur hanche->sol en pixels (le sol ~ niveau des chevilles)
                hauteur_hanche_px = abs(cheville_y - hanche_y)

                # ECHELLE : metres par pixel = hauteur reelle / hauteur en pixels
                if hauteur_hanche_px > 10:
                    echelles.append(hauteur_hanche_reelle_m / hauteur_hanche_px)

                positions_cheville_g.append((frame_idx, cheville_g.x * w, cheville_g.y * h))
                positions_cheville_d.append((frame_idx, cheville_d.x * w, cheville_d.y * h))

            frame_idx += 1

    cap.release()

    if len(echelles) == 0:
        return {"erreur": "aucune posture detectee dans la video"}

    # echelle moyenne (metres par pixel)
    echelle = sum(echelles) / len(echelles)

    # 3) Detecter les pas et mesurer leur longueur
    longueurs = detecter_pas(positions_cheville_g, echelle)
    longueurs += detecter_pas(positions_cheville_d, echelle)

    if len(longueurs) == 0:
        return {"erreur": "aucun pas detecte"}

    foulee_moyenne = sum(longueurs) / len(longueurs)

    return {
        "foulee_m": round(foulee_moyenne, 3),
        "nb_pas_detectes": len(longueurs),
        "echelle_m_par_px": round(echelle, 6),
    }


def detecter_pas(positions, echelle):
    """Detecte les moments ou le pied se pose (extremes de position en X)
    et mesure la distance entre deux poses successives."""
    if len(positions) < 5:
        return []

    xs = [p[1] for p in positions]

    # on cherche les 'extremes' locaux : quand le pied arrete d'avancer
    poses = []
    for i in range(2, len(xs) - 2):
        # un pied pose = point ou la position en X change de direction
        if (xs[i] - xs[i - 2]) * (xs[i + 2] - xs[i]) < 0:
            poses.append(xs[i])

    # distance entre deux poses successives, convertie en metres
    longueurs = []
    for i in range(1, len(poses)):
        dist_px = abs(poses[i] - poses[i - 1])
        dist_m = dist_px * echelle
        # filtre les valeurs aberrantes (un pas humain fait ~0.3 a 1 m)
        if 0.2 < dist_m < 1.5:
            longueurs.append(dist_m)

    return longueurs


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
