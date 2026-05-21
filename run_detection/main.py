import time
import threading
import queue
from config_loader import load_config
from db            import start_trajet, insert_mesure, end_trajet
from CamLive       import run_detection

def main():
    cfg = load_config()
    print(f"⚙️  Config chargée — conducteur={cfg.id_conducteur} | son={'ON' if cfg.sound_enabled else 'OFF'}")
    trajet_id  = start_trajet(cfg)
    start_time = time.time()
    db_queue = queue.Queue()

    def db_worker():
        while True:
            item = db_queue.get()
            if item is None:
                break
            t_ms, ouv, alerte = item
            try:
                insert_mesure(cfg=cfg, id_trajet=trajet_id, temps_ms=t_ms, ouverture_oeil=ouv, alerte_visuelle=alerte)
                print(f"[DB] t={t_ms}ms | œil={ouv:.1f}% | {'ALERTE' if alerte else 'OK'}")
            except Exception as e:
                print(f"[DB]  Erreur : {e}")
            finally:
                db_queue.task_done()

    worker = threading.Thread(target=db_worker, daemon=True)
    worker.start()
    last_send = [0.0]

    def on_mesure(temps_ms, ouverture_oeil, alerte_visuelle):
        now = time.time()
        if now - last_send[0] < cfg.send_interval:
            return
        last_send[0] = now
        db_queue.put((temps_ms, ouverture_oeil, alerte_visuelle))

    try:
        run_detection(cfg=cfg, on_mesure=on_mesure, start_time_ref=start_time)
    finally:
        db_queue.put(None)
        worker.join()
        end_trajet(cfg, trajet_id)

if __name__ == "__main__":
    main()