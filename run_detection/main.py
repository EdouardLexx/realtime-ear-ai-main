import time
from db import start_trajet, insert_mesure, end_trajet
from CamLive import run_detection

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

ID_CONDUCTEUR     = 1      # à adapter selon ton conducteur
DB_SEND_INTERVAL  = 1.0    # secondes entre chaque envoi en base (évite le flood)

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    trajet_id  = start_trajet(ID_CONDUCTEUR)
    start_time = time.time()

    # État partagé entre le callback et la boucle
    last_db_send = [0.0]   # liste pour pouvoir la modifier dans le closure

    def on_mesure(temps_ms: int, ouverture_oeil: float, alerte_visuelle: int):
        """Reçoit les données de cam.py et les envoie en base à intervalle régulier."""
        now = time.time()
        if now - last_db_send[0] < DB_SEND_INTERVAL:
            return  # pas encore le moment d'envoyer

        last_db_send[0] = now

        insert_mesure(
            id_trajet       = trajet_id,
            temps_ms        = temps_ms,
            ouverture_oeil  = ouverture_oeil,
            alerte_visuelle = alerte_visuelle,
            # rythme_cardiaque et alerte_sonore laissés à 0
            # → branche les capteurs ici quand tu les auras
        )

        status = "🔴 ALERTE" if alerte_visuelle else "🟢 OK"
        print(f"[DB] t={temps_ms}ms | œil={ouverture_oeil:.1f}% | {status}")

    try:
        run_detection(on_mesure=on_mesure, start_time_ref=start_time)
    finally:
        end_trajet(trajet_id)


if __name__ == "__main__":
    main()
