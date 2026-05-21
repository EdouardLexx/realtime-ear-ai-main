import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass
class Config:
    # Conducteur
    id_conducteur:    int

    # Base de données
    db_host:          str
    db_port:          int
    db_user:          str
    db_password:      str
    db_name:          str

    # Détection yeux
    max_ear:          float
    closed_threshold: float
    alert_duration:   float
    print_interval:   float

    # Enregistrement
    send_interval:    float

    # Son
    sound_enabled:    bool
    sound_file:       str

    # Capteur cardiaque
    hr_enabled:       bool
    hr_i2c_bus:       int
    hr_int_pin:       int
    hr_alert_low:     int
    hr_alert_high:    int


def load_config(path: str = "config.xml") -> Config:
    """Charge config.xml — cherche toujours à côté de ce fichier si chemin relatif."""
    if not os.path.isabs(path) and not os.path.exists(path):
        path = os.path.join(os.path.dirname(__file__), path)

    tree = ET.parse(path)
    root = tree.getroot()

    def get(tag: str) -> str:
        node = root.find(tag)
        if node is None or node.text is None:
            raise ValueError(f"Balise manquante dans config.xml : <{tag}>")
        return node.text.strip()

    return Config(
        # Conducteur
        id_conducteur    = int(get("conducteur/id")),

        # BDD
        db_host          = get("database/host"),
        db_port          = int(get("database/port")),
        db_user          = get("database/user"),
        db_password      = get("database/password"),
        db_name          = get("database/name"),

        # Détection yeux
        max_ear          = float(get("detection/max_ear")),
        closed_threshold = float(get("detection/closed_threshold")),
        alert_duration   = float(get("detection/alert_duration")),
        print_interval   = float(get("detection/print_interval")),

        # Enregistrement
        send_interval    = float(get("recording/send_interval")),

        # Son
        sound_enabled    = get("sound/enabled").lower() == "true",
        sound_file       = get("sound/file"),

        # Capteur cardiaque
        hr_enabled       = get("heart_rate/enabled").lower() == "true",
        hr_i2c_bus       = int(get("heart_rate/i2c_bus")),
        hr_int_pin       = int(get("heart_rate/int_pin")),
        hr_alert_low     = int(get("heart_rate/alert_bpm_low")),
        hr_alert_high    = int(get("heart_rate/alert_bpm_high")),
    )
