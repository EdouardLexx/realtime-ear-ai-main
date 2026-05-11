import cv2
import numpy as np
import mediapipe as mp
import time
import sys
from typing import Callable, Optional

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

LEFT_EYE_LANDMARKS  = [362, 385, 387, 263, 373, 380]
RIGHT_EYE_LANDMARKS = [33,  160, 158, 133, 153, 144]

MAX_EAR              = 0.35
CLOSED_EYE_THRESHOLD = 0.15
PRINT_INTERVAL       = 0.5   # secondes entre impressions terminal
ALERT_DURATION       = 2.0   # secondes avant alerte


# ─────────────────────────────────────────────
# Fonctions utilitaires
# ─────────────────────────────────────────────

def _denormalize(landmark, w: int, h: int):
    x = max(0, min(w - 1, int(landmark.x * w)))
    y = max(0, min(h - 1, int(landmark.y * h)))
    return (x, y)


def _eye_aspect_ratio(eye_pts):
    A = np.linalg.norm(np.array(eye_pts[1]) - np.array(eye_pts[5]))
    B = np.linalg.norm(np.array(eye_pts[2]) - np.array(eye_pts[4]))
    C = np.linalg.norm(np.array(eye_pts[0]) - np.array(eye_pts[3]))
    ear = (A + B) / (2.0 * C) if C != 0 else 0.0
    return ear


def _ear_to_percent(ear: float) -> float:
    if ear < CLOSED_EYE_THRESHOLD:
        return 0.0
    return min(ear / MAX_EAR * 100, 100.0)


# ─────────────────────────────────────────────
# Boucle principale de détection
# ─────────────────────────────────────────────

def run_detection(
    on_mesure: Optional[Callable[[int, float, int], None]] = None,
    start_time_ref: Optional[float] = None,
) -> None:
    """Lance la détection en temps réel.

    Paramètres
    ----------
    on_mesure : callback appelé à chaque mesure avec :
        - temps_ms        (int)   : temps écoulé depuis le début du trajet
        - ouverture_oeil  (float) : moyenne des deux yeux en %
        - alerte_visuelle (int)   : 1 si yeux fermés ≥ ALERT_DURATION, sinon 0
    start_time_ref : timestamp de début du trajet (time.time()).
        Si None, l'horloge démarre au lancement de cette fonction.
    """
    t0 = start_time_ref if start_time_ref is not None else time.time()

    # ── Webcam ──
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Erreur : webcam inaccessible", file=sys.stderr)
        sys.exit(1)
    print("✅ Webcam détectée")

    cv2.namedWindow("Détection ouverture yeux (Live) — q pour quitter", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Détection ouverture yeux (Live) — q pour quitter", 1000, 700)

    mp_facemesh      = mp.solutions.face_mesh
    last_print       = 0.0
    closed_start     = None  # heure à laquelle les yeux se sont fermés
    alerte_active    = False  # True quand l'alerte est déclenchée

    with mp_facemesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ) as face_mesh:
        try:
            while True:
                ret, frame = cap.read()
                if not ret or frame is None:
                    print("Aucun frame reçu — arrêt.", file=sys.stderr)
                    break

                frame        = cv2.flip(frame, 1)
                h, w, _      = frame.shape
                rgb          = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                results      = face_mesh.process(rgb)
                rgb.flags.writeable = True

                left_pct = right_pct = None
                alerte_visuelle = 0

                if results.multi_face_landmarks:
                    lm = results.multi_face_landmarks[0]

                    left_pts  = [_denormalize(lm.landmark[i], w, h) for i in LEFT_EYE_LANDMARKS]
                    right_pts = [_denormalize(lm.landmark[i], w, h) for i in RIGHT_EYE_LANDMARKS]

                    # ── Dessin des points ──
                    for pts in (left_pts, right_pts):
                        for idx, p in enumerate(pts, start=1):
                            cv2.circle(frame, p, 2, (0, 255, 0), -1)
                            cv2.putText(frame, str(idx), (p[0]+3, p[1]-3),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

                    # ── EAR → pourcentage ──
                    left_ear  = _eye_aspect_ratio(left_pts)
                    right_ear = _eye_aspect_ratio(right_pts)
                    left_pct  = _ear_to_percent(left_ear)
                    right_pct = _ear_to_percent(right_ear)

                    avg_pct = (left_pct + right_pct) / 2.0

                    # ── Gestion de l'alerte ──
                    yeux_fermes = (left_pct == 0.0 and right_pct == 0.0)

                    if yeux_fermes:
                        if closed_start is None:
                            closed_start = time.time()
                        duree_fermee = time.time() - closed_start
                        if duree_fermee >= ALERT_DURATION:
                            alerte_visuelle = 1
                            alerte_active   = True
                            cv2.putText(
                                frame, "YEUX FERMES !",
                                (int(w / 6), int(h / 2)),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3,
                            )
                    else:
                        if alerte_active:
                            print("✅ Yeux rouverts — alerte levée.")
                            alerte_active = False
                        closed_start = None

                    # ── Couleurs texte ──
                    c_left  = (0, 0, 255) if left_pct  == 0.0 else (0, 255, 0)
                    c_right = (0, 0, 255) if right_pct == 0.0 else (0, 255, 0)
                    cv2.putText(frame, f"D: {left_pct:.1f}%",  (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, c_left,  2)
                    cv2.putText(frame, f"G: {right_pct:.1f}%", (10, 70),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, c_right, 2)

                    # ── Callback vers main.py ──
                    if on_mesure is not None:
                        temps_ms = int((time.time() - t0) * 1000)
                        on_mesure(temps_ms, avg_pct, alerte_visuelle)

                # ── Affichage ──
                cv2.imshow("Détection ouverture yeux (Live) — q pour quitter", frame)

                # ── Log terminal ──
                now = time.time()
                if now - last_print >= PRINT_INTERVAL:
                    if left_pct is not None:
                        print(
                            f"Oeil droit: EAR={left_ear:.3f}  %={left_pct:.1f} | "
                            f"Oeil gauche: EAR={right_ear:.3f}  %={right_pct:.1f} | "
                            f"Alerte={alerte_visuelle}"
                        )
                    else:
                        print("Aucun visage détecté")
                    last_print = now

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

        except KeyboardInterrupt:
            print("Interrompu par l'utilisateur.")
        finally:
            cap.release()
            cv2.destroyAllWindows()
