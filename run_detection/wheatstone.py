"""
wheatstone.py
-------------
Lecture du pont de Wheatstone via ADS1115 (I2C).

Câblage (schéma haut-gauche) :
  ADS1115 SDA  → GPIO2 (I2C1 SDA)  — partagé avec MAX30102
  ADS1115 SCL  → GPIO3 (I2C1 SCL)  — partagé avec MAX30102
  ADS1115 ADDR → GND               → adresse I2C = 0x48
  ADS1115 VDD  → +3V3
  ADS1115 GND  → GND

  Pont de Wheatstone (J7) → AIN0 / AIN1 (mesure différentielle)
  Résistance variable (J6) → AIN2 (mesure single-ended)

Dépendances :
  pip install adafruit-circuitpython-ads1x15
"""

import time
import threading

try:
    import board
    import busio
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn
    ADS_AVAILABLE = True
except ImportError:
    ADS_AVAILABLE = False


# Gain ADS1115 → plage de mesure
# GAIN  1  → ±4.096 V
# GAIN  2  → ±2.048 V
# GAIN  4  → ±1.024 V  ← bon pour pont alimentation 3.3V
# GAIN  8  → ±0.512 V
# GAIN  16 → ±0.256 V
DEFAULT_GAIN = 4


class WheatstoneReader:
    """
    Lit en continu l'ADS1115 dans un thread dédié.

    Expose :
      .voltage_diff   : tension différentielle AIN0-AIN1 (pont de Wheatstone)
      .voltage_var    : tension single-ended AIN2 (résistance variable)
      .raw_diff       : valeur ADC brute différentielle
    """

    def __init__(self, i2c_bus: int = 1, address: int = 0x48,
                 gain: int = DEFAULT_GAIN, sample_rate: float = 0.1):
        self._address     = address
        self._gain        = gain
        self._sample_rate = sample_rate   # secondes entre lectures
        self._stop_event  = threading.Event()
        self._thread      = None

        # Valeurs exposées (thread-safe pour float en CPython)
        self.voltage_diff: float = 0.0
        self.voltage_var:  float = 0.0
        self.raw_diff:     int   = 0
        self.ready:        bool  = False

        if not ADS_AVAILABLE:
            print("⚠️  adafruit-ads1x15 non installé — ADS1115 simulé")
            print("    pip install adafruit-circuitpython-ads1x15")

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="Wheatstone-Reader"
        )
        self._thread.start()
        print(f"⚖️  WheatstoneReader démarré (addr=0x{self._address:02X}, gain={self._gain})")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)
        print("⚖️  WheatstoneReader arrêté.")

    def _run(self):
        if not ADS_AVAILABLE:
            # Mode simulation : valeurs fixes pour dev sans matériel
            while not self._stop_event.is_set():
                self.voltage_diff = 0.012   # ~12 mV (pont équilibré)
                self.voltage_var  = 1.65
                self.raw_diff     = 150
                self.ready        = True
                self._stop_event.wait(timeout=self._sample_rate)
            return

        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            ads = ADS.ADS1115(i2c, address=self._address, gain=self._gain)

            # Mesure différentielle AIN0-AIN1 → pont de Wheatstone
            chan_diff = AnalogIn(ads, ADS.P0, ADS.P1)
            # Mesure single-ended AIN2 → résistance variable
            chan_var  = AnalogIn(ads, ADS.P2)

            print("✅ ADS1115 détecté")
            self.ready = True

            while not self._stop_event.is_set():
                try:
                    self.voltage_diff = chan_diff.voltage
                    self.raw_diff     = chan_diff.value
                    self.voltage_var  = chan_var.voltage
                except Exception as e:
                    print(f"[ADS1115] Erreur lecture : {e}")

                self._stop_event.wait(timeout=self._sample_rate)

        except Exception as e:
            print(f"❌ ADS1115 non initialisé : {e}")
            print("   Vérifie le câblage I2C et l'adresse (sudo i2cdetect -y 1)")
