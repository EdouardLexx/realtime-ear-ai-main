import time
import threading
import queue
from config_loader import load_config
from db            import start_trajet, insert_mesure, end_trajet
from CamLive       import run_detection
from heart_rate    import HeartRateMonitor


def main():
    # ── Config ──
    cfg = load_config("config.xml")
    print(
        f"⚙️  Config chargée — "
        f"conducteur={cfg.id_conducteur} | "
        f"son={'ON' if cfg.sound_enabled else 'OFF'} | "
        f"capteur cardiaque={'ON' if cfg.hr_enabled else 'OFF'}"
    )

    # ── Capteur cardiaque ──
    hr_monitor = None
    if cfg.hr_enabled:
        try:
            hr_monitor = HeartRateMonitor(
                i2c_bus  = cfg.hr_i2c_bus,
                int_pin  = cfg.hr_int_pin,
            )
            hr_monitor.start()
        except Exception as e:
            print(f"⚠️  Capteur cardiaque désactivé : {e}")
            hr_monitor = None

    # ── Trajet BDD ──
    trajet_id  = start_trajet(cfg)
    start_time = time.time()

    # ── Thread BDD (non bloquant pour la cam) ──
    db_queue = queue.Queue()

    def db_worker():
        while True:
            item = db_queue.get()
            if item is None:
                break
            t_ms, ouv, alerte_vis, bpm, alerte_son = item
            try:
                insert_mesure(
                    cfg              = cfg,
                    id_trajet        = trajet_id,
                    temps_ms         = t_ms,
                    ouverture_oeil   = ouv,
                    alerte_visuelle  = alerte_vis,
                    rythme_cardiaque = bpm,
                    alerte_sonore    = alerte_son,
                )
                status_yeux  = "👁️ ALERTE YEUX"  if alerte_vis else "👁️ OK"
                status_coeur = f"💓 {bpm} BPM"
                if alerte_son:
                    status_coeur += " ⚠️ ALERTE BPM"
                print(f"[DB] t={t_ms}ms | œil={ouv:.1f}% | {status_yeux} | {status_coeur}")
            except Exception as e:
                print(f"[DB] ⚠️  Erreur envoi : {e}")
            finally:
                db_queue.task_done()

    worker = threading.Thread(target=db_worker, daemon=True, name="DB-Worker")
    worker.start()

    # ── Callback cam → BDD ──
    last_send = [0.0]

    def on_mesure(temps_ms: int, ouverture_oeil: float, alerte_visuelle: int):
        now = time.time()
        if now - last_send[0] < cfg.send_interval:
            return
        last_send[0] = now

        # Lecture BPM depuis le thread capteur
        bpm         = 0
        alerte_bpm  = 0
        if hr_monitor is not None:
            bpm = int(round(hr_monitor.bpm))
            if hr_monitor.finger_present and bpm > 0:
                if bpm < cfg.hr_alert_low or bpm > cfg.hr_alert_high:
                    alerte_bpm = 1

        db_queue.put((temps_ms, ouverture_oeil, alerte_visuelle, bpm, alerte_bpm))

    # ── Lancement caméra ──
    try:
        run_detection(cfg=cfg, on_mesure=on_mesure, start_time_ref=start_time)
    finally:
        # Arrêt propre
        if hr_monitor is not None:
            hr_monitor.stop()
        db_queue.put(None)
        worker.join()
        end_trajet(cfg, trajet_id)


if __name__ == "__main__":
    main()
