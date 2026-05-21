"""
vibrator.py
-----------
Commande du vibreur via transistor PN2222A sur GPIO Raspberry Pi.

Câblage (schéma bas-droite) :
  GPIO "Commande moteur" → R3 (330Ω) → Base PN2222A
  Collecteur PN2222A → Moteur → +3V3
  Émetteur PN2222A   → GND
  D1/D2 1N4007       → roue libre anti-surtension

Le GPIO utilisé est GPIO12 (PWM0) ou GPIO13 (PWM1) selon le schéma
"Commande moteur" branché sur PWM0/PWM1 du Raspberry Pi.
"""

import threading
import time

try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except ImportError:
    RPI_AVAILABLE = False


class Vibrator:
    """
    Contrôle le vibreur en PWM.

    Modes disponibles :
      - pulse(duration, duty)  : vibration unique pendant `duration` secondes
      - pattern(on, off, reps) : schéma on/off répété `reps` fois
      - stop()                 : arrêt immédiat
    """

    def __init__(self, gpio_pin: int = 12, frequency: int = 100):
        self._pin  = gpio_pin
        self._freq = frequency
        self._pwm  = None
        self._lock = threading.Lock()
        self._active_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        if not RPI_AVAILABLE:
            print("⚠️  RPi.GPIO non disponible — vibreur simulé (logs uniquement)")
            return

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self._pin, GPIO.OUT, initial=GPIO.LOW)
        self._pwm = GPIO.PWM(self._pin, self._freq)
        self._pwm.start(0)
        print(f"🔧 Vibreur initialisé sur GPIO{self._pin} ({self._freq} Hz PWM)")

    # ── API publique ─────────────────────────────────────────────────────────

    def pulse(self, duration: float = 1.0, duty: int = 80):
        """Vibre pendant `duration` secondes à `duty`% (0-100)."""
        self._launch(self._do_pulse, duration, duty)

    def pattern(self, on: float = 0.3, off: float = 0.2, reps: int = 5, duty: int = 80):
        """Schéma répété : vibre `on`s, pause `off`s, × `reps`."""
        self._launch(self._do_pattern, on, off, reps, duty)

    def stop(self):
        """Arrête immédiatement toute vibration."""
        self._stop_event.set()
        self._set_duty(0)

    def cleanup(self):
        self.stop()
        if self._pwm:
            self._pwm.stop()
        if RPI_AVAILABLE:
            GPIO.cleanup(self._pin)

    # ── Internals ────────────────────────────────────────────────────────────

    def _launch(self, fn, *args):
        """Lance fn dans un thread, annule le précédent si actif."""
        self._stop_event.set()
        if self._active_thread and self._active_thread.is_alive():
            self._active_thread.join(timeout=1.0)
        self._stop_event.clear()
        self._active_thread = threading.Thread(target=fn, args=args, daemon=True)
        self._active_thread.start()

    def _set_duty(self, duty: int):
        if self._pwm:
            self._pwm.ChangeDutyCycle(duty)
        else:
            if duty > 0:
                print(f"[VIBREUR SIM] ON duty={duty}%")
            else:
                print("[VIBREUR SIM] OFF")

    def _do_pulse(self, duration: float, duty: int):
        self._set_duty(duty)
        start = time.time()
        while not self._stop_event.is_set():
            if time.time() - start >= duration:
                break
            time.sleep(0.01)
        self._set_duty(0)

    def _do_pattern(self, on: float, off: float, reps: int, duty: int):
        for _ in range(reps):
            if self._stop_event.is_set():
                break
            self._set_duty(duty)
            self._stop_event.wait(timeout=on)
            if self._stop_event.is_set():
                break
            self._set_duty(0)
            self._stop_event.wait(timeout=off)
        self._set_duty(0)
