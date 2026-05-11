import os
import time
import mysql.connector
from mysql.connector import Error, errorcode

# Charger un fichier .env s'il existe (optionnel)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


# ─────────────────────────────────────────────
# Connexion
# ─────────────────────────────────────────────

def get_connection():
    """Crée une connexion MariaDB/MySQL depuis les variables d'environnement.

    Variables supportées (valeurs par défaut entre parenthèses) :
      DB_HOST     (servrc.diskstation.me)
      DB_PORT     (3306)
      DB_USER     (Marie)
      DB_PASSWORD ("")
      DB_NAME     (Attention_conducteur)
    """
    host     = os.getenv("DB_HOST",     "servrc.diskstation.me")
    port     = int(os.getenv("DB_PORT", "3306"))
    user     = os.getenv("DB_USER",     "Marie")
    password = os.getenv("DB_PASSWORD", "OCV5Ms!43T(9DJTF")
    database = os.getenv("DB_NAME",     "Attention_conducteur")

    try:
        conn = mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            connection_timeout=5,
        )
        return conn
    except Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            raise SystemExit(
                "Erreur d'authentification. Vérifie DB_USER / DB_PASSWORD."
            ) from err
        if err.errno == errorcode.ER_BAD_DB_ERROR:
            raise SystemExit(
                f"La base '{database}' n'existe pas. Vérifie DB_NAME."
            ) from err
        raise SystemExit(f"Connexion échouée : {err}") from err


# ─────────────────────────────────────────────
# Trajets
# ─────────────────────────────────────────────

def start_trajet(id_conducteur: int) -> int:
    """Crée un nouveau trajet en base et retourne son id."""
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO trajets (id_conducteur, debut_log) VALUES (%s, NOW())",
            (id_conducteur,)
        )
        conn.commit()
        trajet_id = cursor.lastrowid
    finally:
        cursor.close()
        conn.close()

    print(f"🚗 Trajet démarré  (id_trajet = {trajet_id})")
    return trajet_id


def end_trajet(id_trajet: int) -> None:
    """Marque la fin du trajet dans la base."""
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE trajets SET fin_log = NOW() WHERE id_trajet = %s",
            (id_trajet,)
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    print(f" Trajet {id_trajet} terminé !")


# ─────────────────────────────────────────────
# Mesures
# ─────────────────────────────────────────────

def insert_mesure(
    id_trajet:        int,
    temps_ms:         int,
    ouverture_oeil:   float,   # pourcentage moyen des deux yeux (0–100)
    alerte_visuelle:  int,     # 1 si yeux fermés ≥ ALERT_DURATION, sinon 0
    rythme_cardiaque: int = 0, # 0 si non dispo
    alerte_sonore:    int = 0, # 0 si non dispo
) -> None:
    """Insère une mesure en base."""
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO mesures
                (id_trajet, temps_ms, ouverture_oeil,
                 rythme_cardiaque, alerte_visuelle, alerte_sonore)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                id_trajet,  
                int(temps_ms),
                float(ouverture_oeil),
                int(rythme_cardiaque),
                int(alerte_visuelle),
                int(alerte_sonore),
            ),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()
