from dataclasses import dataclass, field
from typing import List
import threading
import time
import logging

log = logging.getLogger(__name__)

try:
    from gpiozero import MCP3008, OutputDevice, DigitalInputDevice
except ImportError:
    MCP3008 = None
    OutputDevice = None
    DigitalInputDevice = None


class HardwareError(RuntimeError):
    """Hardware cannot safely execute the command."""


@dataclass
class HardwareConfig:
    pump_pin: int = 17
    valve_pin: int = 27
    moisture_channels: List[int] = field(default_factory=lambda: [0, 1, 2])
    mode: str = "real"
    flow_pin: int | None = None
    flow_pull_up: bool = True
    pump_active_high: bool = True
    valve_active_high: bool = True
    valve_enabled: bool = True
    water_level_pin: int | None = None

    def __post_init__(self):
        if self.mode not in ("real", "simulation"):
            raise ValueError("HARDWARE_MODE musi mieć wartość real albo simulation.")
        if type(self.valve_enabled) is not bool:
            raise ValueError("VALVE_ENABLED musi mieć wartość logiczną.")
        pins = [self.pump_pin]
        if self.valve_enabled:
            pins.append(self.valve_pin)
        pins.extend(pin for pin in (self.flow_pin, self.water_level_pin) if pin is not None)
        if any(type(pin) is not int or not 0 <= pin <= 27 for pin in pins):
            raise ValueError(
                "Numery pinów BCM muszą być liczbami całkowitymi od 0 do 27.")
        if len(set(pins)) != len(pins):
            raise ValueError("Włączone urządzenia muszą używać różnych pinów GPIO.")
        if any(type(value) is not bool for value in (self.pump_active_high, self.valve_active_high)):
            raise ValueError("Polaryzacja pompy i zaworu musi mieć wartość logiczną.")
        if type(self.flow_pull_up) is not bool:
            raise ValueError("FLOW_PULL_UP musi mieć wartość logiczną.")
        if any(type(ch) is not int or not 0 <= ch <= 7 for ch in self.moisture_channels):
            raise ValueError("Kanały MCP3008 muszą być liczbami całkowitymi od 0 do 7.")
        if len(set(self.moisture_channels)) != len(self.moisture_channels):
            raise ValueError("Kanały MCP3008 nie mogą się powtarzać.")
        if self.moisture_channels and set(pins) & {7, 8, 9, 10, 11}:
            raise ValueError(
                "Piny urządzeń nie mogą pokrywać się z pinami SPI przetwornika MCP3008 (7–11).")


def build_hardware_config(config):
    def integer(value):
        if type(value) is int:
            return value
        if isinstance(value, str):
            return int(value)
        raise ValueError(
            "Numery pinów i kanałów w konfiguracji sprzętu muszą być całkowite.")

    def boolean(name):
        value = config.get(name, True)
        if isinstance(value, str) and value in ("0", "1"):
            return value == "1"
        if type(value) is not bool:
            raise ValueError(f"{name} musi mieć wartość 0 albo 1.")
        return value

    raw = config.get("MOISTURE_CHANNELS", "0,1,2")
    if isinstance(raw, str):
        channels = [] if not raw.strip() else [integer(part.strip())
                                               for part in raw.split(",")]
    elif isinstance(raw, (list, tuple)):
        channels = [integer(part) for part in raw]
    else:
        raise ValueError("MOISTURE_CHANNELS musi być listą kanałów rozdzielonych przecinkami.")
    flow_pin = config.get("FLOW_PIN")
    water_pin = config.get("WATER_LEVEL_PIN")
    pull_up = config.get("FLOW_PULL_UP", True)
    if isinstance(pull_up, str):
        if pull_up not in ("0", "1"):
            raise ValueError("FLOW_PULL_UP musi mieć wartość 0 albo 1.")
        pull_up = pull_up == "1"
    return HardwareConfig(
        pump_pin=integer(config.get("PUMP_PIN", 17)),
        valve_pin=integer(config.get("VALVE_PIN", 27)),
        moisture_channels=channels,
        mode=config.get("HARDWARE_MODE", "real"),
        flow_pin=None if flow_pin in (None, "") else integer(flow_pin),
        flow_pull_up=pull_up,
        pump_active_high=boolean("PUMP_ACTIVE_HIGH"),
        valve_active_high=boolean("VALVE_ACTIVE_HIGH"),
        valve_enabled=boolean("VALVE_ENABLED"),
        water_level_pin=None if water_pin in (None, "") else integer(water_pin),
    )


class WateringHardware:
    """GPIO access; the application controller serializes all operations."""

    def __init__(self, config: HardwareConfig):
        self.config = config
        self.simulated = config.mode == "simulation"
        self.available = False
        self.error = None
        self.closed = False
        self.pump = None
        self.valve = None
        self.sensors = []
        self.flow_input = None
        self.water_level_input = None
        self._flow_lock = threading.Lock()
        self._flow_pulses = 0
        self._last_pulse = None
        self._pump_state = False
        self._valve_state = False
        if self.simulated:
            return
        try:
            if OutputDevice is None or MCP3008 is None:
                raise HardwareError(
                    "Biblioteka gpiozero jest niedostępna. Zainstaluj zależności obsługi sprzętu.")
            self.pump = OutputDevice(
                config.pump_pin, active_high=config.pump_active_high, initial_value=False)
            if config.valve_enabled:
                self.valve = OutputDevice(
                    config.valve_pin, active_high=config.valve_active_high, initial_value=False)
            if config.water_level_pin is not None:
                self.water_level_input = DigitalInputDevice(config.water_level_pin, pull_up=True)
            # Append individually so partially initialized sensors can be closed.
            for channel in config.moisture_channels:
                self.sensors.append(MCP3008(channel=channel))
            if config.flow_pin is not None:
                self.flow_input = DigitalInputDevice(config.flow_pin, pull_up=config.flow_pull_up)
                self.flow_input.when_activated = self._record_pulse
            self.available = True
        except Exception as exc:
            log.exception("Nie udało się uruchomić sprzętu")
            self.error = "Nie udało się uruchomić sprzętu. Sprawdź konfigurację GPIO i połączenia."
            self.safe_off()
            self._close_devices()

    @property
    def ready(self):
        return not self.closed and not self.error and (self.available or self.simulated)

    def _read_state(self, device, simulated_state):
        if self.simulated:
            return simulated_state
        if device is None or self.closed:
            return None
        try:
            return bool(device.value)
        except Exception as exc:
            log.exception("Nie udało się odczytać stanu GPIO")
            self.error = "Nie udało się odczytać stanu GPIO."
            return None

    def status(self):
        pump_on = self._read_state(self.pump, self._pump_state)
        valve_open = self._read_state(self.valve, self._valve_state) if self.config.valve_enabled else None
        return {
            "available": self.available,
            "simulated": self.simulated,
            "mode": self.config.mode,
            "ready": self.ready,
            "error": self.error,
            "pump_on": pump_on,
            "valve_open": valve_open,
            "valve_enabled": self.config.valve_enabled,
            "water_level": self.water_level(),
            "moisture_channels": self.config.moisture_channels,
            "flow_configured": self.config.flow_pin is not None,
        }

    def _set(self, name, on):
        if on and not self.ready:
            raise HardwareError(
                self.error or "Sprzęt jest niedostępny lub został wyłączony.")
        device = getattr(self, name)
        if self.simulated:
            setattr(self, f"_{name}_state", on)
        elif device is not None:
            try:
                device.on() if on else device.off()
            except Exception as exc:
                log.exception("Nie udało się przełączyć urządzenia: %s", name)
                label = "pompę" if name == "pump" else "zawór"
                self.error = f"Nie udało się {'włączyć' if on else 'wyłączyć'} urządzenia: {label}."
                raise HardwareError(self.error) from exc

    def set_pump(self, on: bool):
        self._set("pump", on)

    def set_valve(self, open_value: bool):
        if not self.config.valve_enabled:
            raise HardwareError("Zawór jest wyłączony w konfiguracji.")
        self._set("valve", open_value)

    def water_level(self):
        configured = self.config.water_level_pin is not None
        present = None
        if configured and not self.simulated and not self.closed and self.water_level_input is not None:
            try:
                value = self.water_level_input.value
                if value in (0, 1):
                    present = bool(value)  # pull_up=True: closed to GND is active.
            except Exception:
                log.exception("Nie udało się odczytać poziomu wody")
        return {"configured": configured, "water_present": present,
                "state": ("not_configured" if not configured else
                          "unknown" if present is None else "ok" if present else "low_water")}

    def _record_pulse(self):
        # This callback never takes the controller lock or accesses SQLite.
        with self._flow_lock:
            self._flow_pulses += 1
            self._last_pulse = time.monotonic()

    def flow(self):
        with self._flow_lock:
            return {"configured": self.config.flow_pin is not None,
                    "pulses": self._flow_pulses, "last_pulse": self._last_pulse}

    def safe_off(self):
        """Attempt both outputs even if the first operation fails."""
        errors = []
        actions = [("pump", self.set_pump)]
        if self.config.valve_enabled:
            actions.append(("valve", self.set_valve))
        for name, action in actions:
            try:
                action(False)
            except Exception as exc:
                log.exception("Nie udało się wyłączyć urządzenia: %s", name)
                label = "Pompa" if name == "pump" else "Zawór"
                errors.append(f"{label}: nie udało się wyłączyć urządzenia.")
        if errors:
            self.error = "; ".join(errors)
        return errors

    def read_moisture(self):
        if self.simulated or not self.available:
            # No made-up moisture measurements in simulation mode.
            return [None for _ in self.config.moisture_channels]
        readings = []
        for sensor in self.sensors:
            try:
                readings.append(round(sensor.value, 3))
            except Exception:
                readings.append(None)
        return readings

    def probe(self):
        """Inspect owned GPIO objects without allocating or switching pins."""
        components = []
        devices = [
            ("Pompa", "gpio_output", f"GPIO{self.config.pump_pin}", self.pump),
        ]
        if self.config.valve_enabled:
            devices.append(("Zawór", "gpio_output", f"GPIO{self.config.valve_pin}", self.valve))
        if self.config.water_level_pin is not None:
            devices.append(("Poziom wody", "contact_input", f"GPIO{self.config.water_level_pin}", self.water_level_input))
        if self.config.flow_pin is not None:
            devices.append(("Przepływomierz", "pulse_input", f"GPIO{self.config.flow_pin}", self.flow_input))
        devices.extend(
            (f"Wilgotność — kanał {ch}", "adc_channel", f"MCP3008:CH{ch}",
             self.sensors[index] if index < len(self.sensors) else None)
            for index, ch in enumerate(self.config.moisture_channels)
        )
        for name, kind, location, device in devices:
            component = {"name": name, "type": kind, "location": location}
            if self.simulated:
                component["status"] = "simulated"
            else:
                try:
                    if device is None or self.closed:
                        raise HardwareError(
                            self.error or "Urządzenie jest niedostępne.")
                    component.update(status="ok", value=round(float(device.value), 3),
                                     driver=type(device).__name__)
                except Exception as exc:
                    log.exception("Błąd diagnostyki urządzenia")
                    component.update(status="fail", error=str(exc) if isinstance(exc, HardwareError) else "Nie udało się odczytać stanu urządzenia.")
            components.append(component)
        failed = self.error or self.closed or any(
            c["status"] == "fail" for c in components)
        return {
            "overall_status": "fail" if failed else ("simulated" if self.simulated else "ok"),
            "mode": self.config.mode,
            "error": self.error,
            "physical_operation_verified": False,
            "note": "Sprawdzono wyłącznie dostęp do GPIO/ADC. Nie potwierdza to przepływu wody ani fizycznego działania urządzeń.",
            "components": components,
        }

    def _close_devices(self):
        errors = []
        for device in (self.pump, self.valve, self.flow_input, self.water_level_input, *self.sensors):
            if device is not None:
                try:
                    device.close()
                except Exception as exc:
                    log.exception("Nie udało się zwolnić urządzenia GPIO")
                    errors.append("Nie udało się zwolnić urządzenia GPIO.")
        self.pump = self.valve = None
        self.flow_input = None
        self.water_level_input = None
        self.sensors = []
        self.available = False
        return errors

    def close(self):
        if self.closed:
            return
        errors = self.safe_off()
        errors.extend(self._close_devices())
        self.closed = True
        if errors:
            self.error = "; ".join(errors)


def probe_hardware(config: HardwareConfig):
    """Standalone diagnostic for tests, before starting the application."""
    hardware = WateringHardware(config)
    try:
        return hardware.probe()
    finally:
        hardware.close()
