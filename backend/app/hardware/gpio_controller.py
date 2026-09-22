from dataclasses import dataclass, field
from typing import List
import threading
import time

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

    def __post_init__(self):
        if self.mode not in ("real", "simulation"):
            raise ValueError("HARDWARE_MODE must be real or simulation.")
        pins = (self.pump_pin, self.valve_pin) + (() if self.flow_pin is None else (self.flow_pin,))
        if any(type(pin) is not int or not 0 <= pin <= 27 for pin in pins):
            raise ValueError(
                "Pump and valve pins must be BCM integers from 0 to 27.")
        if len(set(pins)) != len(pins):
            raise ValueError("Pump, valve and flow meter must use different GPIO pins.")
        if type(self.flow_pull_up) is not bool:
            raise ValueError("FLOW_PULL_UP must be a boolean.")
        if any(type(ch) is not int or not 0 <= ch <= 7 for ch in self.moisture_channels):
            raise ValueError("MCP3008 channels must be integers from 0 to 7.")
        if len(set(self.moisture_channels)) != len(self.moisture_channels):
            raise ValueError("MCP3008 channels must not repeat.")
        if self.moisture_channels and set(pins) & {7, 8, 9, 10, 11}:
            raise ValueError(
                "Actuator pins must not overlap the MCP3008 SPI pins (7–11).")


def build_hardware_config(config):
    def integer(value):
        if type(value) is int:
            return value
        if isinstance(value, str):
            return int(value)
        raise ValueError(
            "Hardware configuration requires integer pins/channels.")

    raw = config.get("MOISTURE_CHANNELS", "0,1,2")
    if isinstance(raw, str):
        channels = [] if not raw.strip() else [integer(part.strip())
                                               for part in raw.split(",")]
    elif isinstance(raw, (list, tuple)):
        channels = [integer(part) for part in raw]
    else:
        raise ValueError("MOISTURE_CHANNELS must be a comma-separated list.")
    flow_pin = config.get("FLOW_PIN")
    pull_up = config.get("FLOW_PULL_UP", True)
    if isinstance(pull_up, str):
        if pull_up not in ("0", "1"):
            raise ValueError("FLOW_PULL_UP must be 0 or 1.")
        pull_up = pull_up == "1"
    return HardwareConfig(
        pump_pin=integer(config.get("PUMP_PIN", 17)),
        valve_pin=integer(config.get("VALVE_PIN", 27)),
        moisture_channels=channels,
        mode=config.get("HARDWARE_MODE", "real"),
        flow_pin=None if flow_pin in (None, "") else integer(flow_pin),
        flow_pull_up=pull_up,
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
                    "gpiozero is unavailable. Install the hardware dependencies.")
            self.pump = OutputDevice(
                config.pump_pin, active_high=True, initial_value=False)
            self.valve = OutputDevice(
                config.valve_pin, active_high=True, initial_value=False)
            # Append individually so partially initialized sensors can be closed.
            for channel in config.moisture_channels:
                self.sensors.append(MCP3008(channel=channel))
            if config.flow_pin is not None:
                self.flow_input = DigitalInputDevice(config.flow_pin, pull_up=config.flow_pull_up)
                self.flow_input.when_activated = self._record_pulse
            self.available = True
        except Exception as exc:
            self.error = f"Hardware initialization failed: {exc}"
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
            self.error = f"GPIO state read failed: {exc}"
            return None

    def status(self):
        pump_on = self._read_state(self.pump, self._pump_state)
        valve_open = self._read_state(self.valve, self._valve_state)
        return {
            "available": self.available,
            "simulated": self.simulated,
            "mode": self.config.mode,
            "ready": self.ready,
            "error": self.error,
            "pump_on": pump_on,
            "valve_open": valve_open,
            "moisture_channels": self.config.moisture_channels,
            "flow_configured": self.config.flow_pin is not None,
        }

    def _set(self, name, on):
        if on and not self.ready:
            raise HardwareError(
                self.error or "Hardware is unavailable or closed.")
        device = getattr(self, name)
        if self.simulated:
            setattr(self, f"_{name}_state", on)
        elif device is not None:
            try:
                device.on() if on else device.off()
            except Exception as exc:
                self.error = f"Cannot switch {name} {'on' if on else 'off'}: {exc}"
                raise HardwareError(self.error) from exc

    def set_pump(self, on: bool):
        self._set("pump", on)

    def set_valve(self, open_value: bool):
        self._set("valve", open_value)

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
        for name, action in (("pump", self.set_pump), ("valve", self.set_valve)):
            try:
                action(False)
            except Exception as exc:
                errors.append(f"{name}: {exc}")
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
            ("Pump", "gpio_output", f"GPIO{self.config.pump_pin}", self.pump),
            ("Valve", "gpio_output",
             f"GPIO{self.config.valve_pin}", self.valve),
        ]
        if self.config.flow_pin is not None:
            devices.append(("Flow meter", "pulse_input", f"GPIO{self.config.flow_pin}", self.flow_input))
        devices.extend(
            (f"Moisture CH{ch}", "adc_channel", f"MCP3008:CH{ch}",
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
                            self.error or "Device is unavailable.")
                    component.update(status="ok", value=round(float(device.value), 3),
                                     driver=type(device).__name__)
                except Exception as exc:
                    component.update(status="fail", error=str(exc))
            components.append(component)
        failed = self.error or self.closed or any(
            c["status"] == "fail" for c in components)
        return {
            "overall_status": "fail" if failed else ("simulated" if self.simulated else "ok"),
            "mode": self.config.mode,
            "error": self.error,
            "physical_operation_verified": False,
            "note": "GPIO/ADC access only; this does not verify water flow or physical device operation.",
            "components": components,
        }

    def _close_devices(self):
        errors = []
        for device in (self.pump, self.valve, self.flow_input, *self.sensors):
            if device is not None:
                try:
                    device.close()
                except Exception as exc:
                    errors.append(str(exc))
        self.pump = self.valve = None
        self.flow_input = None
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
