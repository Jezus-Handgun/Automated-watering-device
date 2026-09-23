from collections import deque
from dataclasses import dataclass, asdict
import math
from statistics import median


FIELD_LABELS = {
    "sample_interval_seconds": "odstęp między pomiarami",
    "filter_samples": "liczba próbek filtra",
    "portion_seconds": "limit czasu porcji",
    "soak_seconds": "przerwa na wsiąknięcie",
    "daily_limit_seconds": "dzienny budżet czasu",
    "no_flow_timeout_seconds": "limit oczekiwania na przepływ",
    "dry_raw": "odczyt suchego podłoża",
    "wet_raw": "odczyt mokrego podłoża",
}


def number(value, low, high):
    return type(value) in (int, float) and low <= value <= high and math.isfinite(value)


@dataclass
class Settings:
    enabled: bool = False
    channel: int = 0
    dry_raw: float | None = None
    wet_raw: float | None = None
    start_percent: float = 30
    stop_percent: float = 50
    sample_interval_seconds: int = 10
    filter_samples: int = 3
    portion_seconds: int = 5
    soak_seconds: int = 300
    daily_limit_seconds: int = 120
    portion_mode: str = "time"
    portion_ml: float = 50
    flow_pulses_per_liter: float | None = None
    no_flow_timeout_seconds: int = 5

    def validate(self, channels, flow_configured):
        if type(self.enabled) is not bool:
            raise ValueError("Włączenie automatyki musi mieć wartość logiczną true albo false.")
        if type(self.channel) is not int or not 0 <= self.channel <= 7 or (self.channel not in channels and (channels or self.enabled)):
            raise ValueError("Wybierz skonfigurowany kanał czujnika wilgotności.")
        for key, low, high in (("sample_interval_seconds", 1, 3600), ("filter_samples", 1, 31),
                               ("portion_seconds", 1,
                                600), ("soak_seconds", 1, 86400),
                               ("daily_limit_seconds", 1, 86400), ("no_flow_timeout_seconds", 1, 60)):
            value = getattr(self, key)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(
                    f"Pole „{FIELD_LABELS[key]}” musi być liczbą całkowitą od {low} do {high}.")
        if self.filter_samples % 2 != 1:
            raise ValueError("Liczba próbek filtra musi być nieparzysta.")
        if not number(self.start_percent, 0, 100) or not number(self.stop_percent, 0, 100) or self.start_percent >= self.stop_percent:
            raise ValueError(
                "Progi muszą należeć do zakresu 0–100%, a próg rozpoczęcia musi być niższy od progu zakończenia.")
        for key in ("dry_raw", "wet_raw"):
            value = getattr(self, key)
            if value is not None and not number(value, 0, 1):
                raise ValueError(
                    f"Pole „{FIELD_LABELS[key]}” musi być puste lub zawierać skończoną liczbę od 0 do 1.")
        calibrated = self.dry_raw is not None and self.wet_raw is not None
        if calibrated and abs(self.dry_raw - self.wet_raw) < 0.01:
            raise ValueError(
                "Odczyty suchego i mokrego podłoża muszą różnić się o co najmniej 0,01.")
        if self.portion_mode not in ("time", "volume") or not number(self.portion_ml, 1, 5000):
            raise ValueError(
                "Wybierz porcję odmierzaną czasem lub objętością; objętość musi wynosić od 1 do 5000 ml.")
        if self.flow_pulses_per_liter is not None and not number(self.flow_pulses_per_liter, 1, 1_000_000):
            raise ValueError(
                "Liczba impulsów na litr musi być pusta lub wynosić od 1 do 1000000.")
        if self.enabled:
            if not calibrated:
                raise ValueError(
                    "Przed włączeniem automatyki skalibruj czujnik dla suchego i mokrego podłoża.")
            if self.portion_seconds > self.daily_limit_seconds:
                raise ValueError(
                    "Limit czasu porcji przekracza dzienny budżet podlewania.")
            if self.portion_mode == "volume" and (not flow_configured or self.flow_pulses_per_liter is None):
                raise ValueError(
                    "Automatyczne podlewanie według objętości wymaga skonfigurowanego i skalibrowanego przepływomierza.")
        return self

    def json(self):
        return asdict(self)


class MoistureFilter:
    def __init__(self):
        self.values = {}

    def clear(self):
        self.values.clear()

    def sample(self, channel, raw, settings):
        queue = self.values.setdefault(
            channel, deque(maxlen=settings.filter_samples))
        result = {"channel": channel, "raw_value": raw,
                  "moisture_percent": None, "error": None}
        if not number(raw, 0, 1):
            queue.clear()
            result.update(raw_value=None,
                          error="Brak odczytu czujnika lub niepoprawny pomiar.")
            return result
        # Saturation often indicates an open/disconnected ADC input or invalid range.
        if raw <= 0.001 or raw >= 0.999:
            queue.clear()
            result["error"] = "Odczyt osiągnął granicę zakresu przetwornika ADC. Sprawdź czujnik."
            return result
        queue.append(raw)
        if channel != settings.channel or settings.dry_raw is None or settings.wet_raw is None:
            return result
        if len(queue) < settings.filter_samples:
            result["error"] = "Zbieranie nowych próbek."
            return result
        calibrated = 100 * (median(queue) - settings.dry_raw) / \
            (settings.wet_raw - settings.dry_raw)
        result["moisture_percent"] = round(max(0, min(100, calibrated)), 2)
        return result
