import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass

@dataclass
class Config:
    id_conducteur:    int
    db_host:          str
    db_port:          int
    db_user:          str
    db_password:      str
    db_name:          str
    max_ear:          float
    closed_threshold: float
    alert_duration:   float
    print_interval:   float
    send_interval:    float
    sound_enabled:    bool
    sound_file:       str

def load_config(path: str = "config.xml") -> Config:
    if not os.path.isabs(path) and not os.path.exists(path):
        path = os.path.join(os.path.dirname(__file__), path)
    tree = ET.parse(path)
    root = tree.getroot()

    def get(tag):
        node = root.find(tag)
        if node is None or node.text is None:
            raise ValueError(f"Balise manquante : <{tag}>")
        return node.text.strip()

    return Config(
        id_conducteur    = int(get("conducteur/id")),
        db_host          = get("database/host"),
        db_port          = int(get("database/port")),
        db_user          = get("database/user"),
        db_password      = get("database/password"),
        db_name          = get("database/name"),
        max_ear          = float(get("detection/max_ear")),
        closed_threshold = float(get("detection/closed_threshold")),
        alert_duration   = float(get("detection/alert_duration")),
        print_interval   = float(get("detection/print_interval")),
        send_interval    = float(get("recording/send_interval")),
        sound_enabled    = get("sound/enabled").lower() == "true",
        sound_file       = get("sound/file"),
    )