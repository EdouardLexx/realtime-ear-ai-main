"""
heart_rate.py
-------------
Lecture du capteur MAX30102 en arrière-plan (thread).
Fournit le BPM courant via heart_rate_monitor.bpm

Câblage supposé (schéma J5) :
  MAX30102 SDA  → GPIO2  (I2C1 SDA)
  MAX30102 SCL  → GPIO3  (I2C1 SCL)
  MAX30102 INT  → GPIO23
  MAX30102 VIN  → +1.8V / +3.3V (selon ton régulateur)
  MAX30102 GND  → GND

Dépendances :
  pip install smbus2 numpy RPi.GPIO
  # lib bas-niveau MAX30102 :
  # copier max30102_driver.py dans le même dossier
  # (voir instructions en bas de ce fichier)
"""

import time
import threading
import numpy as np

# ── Constantes registres MAX30102 ──────────────────────────────────────────
MAX30102_ADDRESS      = 0x57

REG_INTR_STATUS_1     = 0x00
REG_INTR_ENABLE_1     = 0x02
REG_FIFO_WR_PTR       = 0x04
REG_OVF_COUNTER       = 0x05
REG_FIFO_RD_PTR       = 0x06
REG_FIFO_DATA         = 0x07
REG_FIFO_CONFIG       = 0x08
REG_MODE_CONFIG       = 0x09
REG_SPO2_CONFIG       = 0x0A
REG_LED1_PA           = 0x0C   # LED rouge
REG_LED2_PA           = 0x0D   # LED IR
REG_PART_ID           = 0xFF

FIFO_SAMPLES          = 100    # nb d'échantillons pour calcul BPM
BPM_BUFFER_SIZE       = 4      # moyenne glissante
FINGER_THRESHOLD      = 50000  # en dessous = pas de doigt


# ── Driver bas niveau ───────────────────────────────────────────────────────

class MAX30102Driver:
    """Driver I2C minimal pour MAX30102 via smbus2."""

    def __init__(self, i2c_bus: int = 1, int_pin: int = 23):
        try:
            import smbus2
        except ImportError:
            raise SystemExit("❌ smbus2 non installé. Lance : pip install smbus2")
        try:
            import RPi.GPIO as GPIO
        except ImportError:
            raise SystemExit("❌ RPi.GPIO non installé. Lance : pip install RPi.GPIO")

        self._bus     = smbus2.SMBus(i2c_bus)
        self._addr    = MAX30102_ADDRESS
        self._int_pin = int_pin
        self._GPIO    = GPIO

        # Vérification présence capteur
        part_id = self._read_byte(REG_PART_ID)
        if part_id != 0x15:
            raise RuntimeError(
                f"MAX30102 non détecté (part_id=0x{part_id:02X}, attendu 0x15). "
                "Vérifie le câblage I2C."
            )

        self._setup_gpio()
        self._init_sensor()

    def _read_byte(self, reg: int) -> int:
        return self._bus.read_byte_data(self._addr, reg)

    def _write_byte(self, reg: int, value: int):
        self._bus.write_byte_data(self._addr, reg, value)

    def _setup_gpio(self):
        self._GPIO.setwarnings(False)
        self._GPIO.setmode(self._GPIO.BCM)
        self._GPIO.setup(self._int_pin, self._GPIO.IN, pull_up_down=self._GPIO.PUD_UP)

    def _init_sensor(self):
        """Reset + configuration HR mode."""
        # Reset
        self._write_byte(REG_MODE_CONFIG, 0x40)
        time.sleep(0.1)

        # Activer interruption FIFO_A_FULL
        self._write_byte(REG_INTR_ENABLE_1, 0xC0)

        # FIFO : moyenne sur 4 échantillons, FIFO_ROLLOVER activé, seuil=17
        self._write_byte(REG_FIFO_CONFIG, 0x4F)

        # Mode HR uniquement (LED rouge seulement)
        self._write_byte(REG_MODE_CONFIG, 0x02)

        # SPO2 : 100 SPS, 18 bits, plage 4096 nA
        self._write_byte(REG_SPO2_CONFIG, 0x27)

        # Intensité LED : ~7 mA
        self._write_byte(REG_LED1_PA, 0x24)
        self._write_byte(REG_LED2_PA, 0x24)

        # Vider pointeurs FIFO
        self._write_byte(REG_FIFO_WR_PTR, 0x00)
        self._write_byte(REG_OVF_COUNTER, 0x00)
        self._write_byte(REG_FIFO_RD_PTR, 0x00)

        # Lire et vider le registre d'interruption
        self._read_byte(REG_INTR_STATUS_1)

    def wait_for_data(self, timeout: float = 1.0) -> bool:
        """Attend l'interruption INT (active basse). Retourne True si donnée dispo."""
        start = time.time()
        while self._GPIO.input(self._int_pin) == 1:
            if time.time() - start > timeout:
                return False
            time.sleep(0.001)
        self._read_byte(REG_INTR_STATUS_1)  # acquitter
        return True

    def get_data_count(self) -> int:
        """Retourne le nombre d'échantillons disponibles dans le FIFO."""
        wr = self._read_byte(REG_FIFO_WR_PTR)
        rd = self._read_byte(REG_FIFO_RD_PTR)
        return (wr - rd) & 0x1F

    def read_fifo(self):
        """Lit un échantillon (red, ir) depuis le FIFO."""
        raw = self._bus.read_i2c_block_data(self._addr, REG_FIFO_DATA, 6)
        red = ((raw[0] & 0x03) << 16) | (raw[1] << 8) | raw[2]
        ir  = ((raw[3] & 0x03) << 16) | (raw[4] << 8) | raw[5]
        return red, ir

    def close(self):
        self._bus.close()
        self._GPIO.cleanup(self._int_pin)


# ── Calcul BPM ──────────────────────────────────────────────────────────────

def _calc_bpm(ir_data: list) -> tuple[float, bool]:
    """
    Calcul BPM par détection de pics sur signal IR.
    Retourne (bpm, valide).
    """
    if len(ir_data) < FIFO_SAMPLES:
        return 0.0, False

    signal = np.array(ir_data[-FIFO_SAMPLES:], dtype=float)

    # Vérif présence doigt
    if np.mean(signal) < FINGER_THRESHOLD:
        return 0.0, False

    # Soustraction tendance (detrend simple)
    signal -= np.mean(signal)

    # Détection de pics (passages par zéro montants)
    zero_crossings = np.where(np.diff(np.sign(signal)) > 0)[0]

    if len(zero_crossings) < 2:
        return 0.0, False

    # Intervalles entre pics → BPM
    # On suppose 100 échantillons = ~1 seconde (100 SPS)
    sample_rate = 100.0
    intervals   = np.diff(zero_crossings) / sample_rate  # en secondes
    mean_interval = np.mean(intervals)

    if mean_interval <= 0:
        return 0.0, False

    bpm = 60.0 / mean_interval

    # Filtre plausibilité
    if not (40 <= bpm <= 200):
        return 0.0, False

    return bpm, True


# ── Thread principal ─────────────────────────────────────────────────────────

class HeartRateMonitor:
    """
    Lance la lecture MAX30102 dans un thread dédié.

    Usage :
        monitor = HeartRateMonitor(int_pin=23)
        monitor.start()
        ...
        bpm = monitor.bpm          # 0 si pas de doigt / pas encore calculé
        ...
        monitor.stop()
    """

    def __init__(self, i2c_bus: int = 1, int_pin: int = 23):
        self._i2c_bus = i2c_bus
        self._int_pin = int_pin
        self._thread  = None
        self._stop_event = threading.Event()

        self.bpm: float = 0.0         # BPM courant (thread-safe en lecture float)
        self.finger_present: bool = False

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="HR-Monitor")
        self._thread.start()
        print(f"💓 HeartRateMonitor démarré (I2C bus={self._i2c_bus}, INT=GPIO{self._int_pin})")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)
        print("💓 HeartRateMonitor arrêté.")

    def _run(self):
        try:
            driver  = MAX30102Driver(i2c_bus=self._i2c_bus, int_pin=self._int_pin)
        except Exception as e:
            print(f"❌ Impossible d'initialiser le MAX30102 : {e}")
            return

        ir_data   = []
        bpm_buffer = []

        try:
            while not self._stop_event.is_set():
                # Attendre donnée disponible via INT
                if not driver.wait_for_data(timeout=1.0):
                    continue

                count = driver.get_data_count()
                while count > 0:
                    try:
                        _, ir = driver.read_fifo()
                        ir_data.append(ir)
                        count -= 1
                    except Exception:
                        break

                # Garder seulement les derniers échantillons
                if len(ir_data) > FIFO_SAMPLES * 2:
                    ir_data = ir_data[-FIFO_SAMPLES:]

                # Calcul BPM dès qu'on a assez d'échantillons
                if len(ir_data) >= FIFO_SAMPLES:
                    bpm, valid = _calc_bpm(ir_data)
                    mean_ir    = np.mean(ir_data[-FIFO_SAMPLES:])
                    self.finger_present = mean_ir >= FINGER_THRESHOLD

                    if valid and self.finger_present:
                        bpm_buffer.append(bpm)
                        if len(bpm_buffer) > BPM_BUFFER_SIZE:
                            bpm_buffer.pop(0)
                        self.bpm = float(np.mean(bpm_buffer))
                    elif not self.finger_present:
                        self.bpm = 0.0
                        bpm_buffer.clear()

        finally:
            driver.close()
