from dataclasses import dataclass, field
import time
from typing import List

try:
    from gpiozero import MCP3008, OutputDevice
except Exception:
    MCP3008 = None
    OutputDevice = None


@dataclass
class HardwareConfig:
    pump_pin: int = 17
    valve_pin: int = 27
    moisture_channels: List[int] = field(default_factory=lambda: [0, 1, 2])


def build_hardware_config(config):
    def _coerce_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    channels_raw = config.get("MOISTURE_CHANNELS", "0,1,2")
    channels = []
    for part in str(channels_raw).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            channels.append(int(part))
        except ValueError:
            continue

    return HardwareConfig(
        pump_pin=_coerce_int(config.get("PUMP_PIN", 17), 17),
        valve_pin=_coerce_int(config.get("VALVE_PIN", 27), 27),
        moisture_channels=channels,
    )


def _get_pin_factory_name(device):
    factory = getattr(device, "pin_factory", None)
    if factory is None and getattr(device, "pin", None) is not None:
        factory = getattr(device.pin, "factory", None)
    return type(factory).__name__ if factory is not None else None


def probe_hardware(config: HardwareConfig):
    report = {
        "overall_status": "ok",
        "components": [],
    }

    def add_component(name, type_name, status, **details):
        component = {
            "name": name,
            "type": type_name,
            "status": status,
        }
        component.update(details)
        report["components"].append(component)
        if status != "ok":
            report["overall_status"] = "fail"
        return component

    if OutputDevice is None:
        add_component(
            "Pump",
            "gpio_output",
            "fail",
            location=f"GPIO{config.pump_pin}",
            pin=config.pump_pin,
            error="gpiozero OutputDevice not available",
        )
        add_component(
            "Valve",
            "gpio_output",
            "fail",
            location=f"GPIO{config.valve_pin}",
            pin=config.valve_pin,
            error="gpiozero OutputDevice not available",
        )
    else:
        for name, pin in (("Pump", config.pump_pin), ("Valve", config.valve_pin)):
            factory_name = None
            try:
                device = OutputDevice(
                    pin, active_high=True, initial_value=False)
                value = device.value
                factory_name = _get_pin_factory_name(device)
                device.close()
                add_component(
                    name,
                    "gpio_output",
                    "ok",
                    driver="OutputDevice",
                    location=f"GPIO{pin}",
                    pin=pin,
                    pin_factory=factory_name,
                    value=float(value),
                )
            except Exception as exc:
                add_component(
                    name,
                    "gpio_output",
                    "fail",
                    driver="OutputDevice",
                    location=f"GPIO{pin}",
                    pin=pin,
                    pin_factory=factory_name,
                    error=str(exc),
                )

    if MCP3008 is None:
        for channel in config.moisture_channels:
            add_component(
                f"Moisture CH{channel}",
                "adc_channel",
                "fail",
                location=f"MCP3008:CH{channel}",
                channel=channel,
                error="gpiozero MCP3008 not available",
            )
    else:
        for channel in config.moisture_channels:
            factory_name = None
            try:
                sensor = MCP3008(channel=channel)
                value = sensor.value
                factory_name = _get_pin_factory_name(sensor)
                sensor.close()
                add_component(
                    f"Moisture CH{channel}",
                    "adc_channel",
                    "ok",
                    driver="MCP3008",
                    location=f"MCP3008:CH{channel}",
                    channel=channel,
                    pin_factory=factory_name,
                    value=round(float(value), 3),
                )
            except Exception as exc:
                add_component(
                    f"Moisture CH{channel}",
                    "adc_channel",
                    "fail",
                    driver="MCP3008",
                    location=f"MCP3008:CH{channel}",
                    channel=channel,
                    pin_factory=factory_name,
                    error=str(exc),
                )

    return report


class WateringHardware:
    def __init__(self, config: HardwareConfig):
        self.config = config
        self.available = OutputDevice is not None and MCP3008 is not None
        self._pump_state = False
        self._valve_state = False

        if self.available:
            self.pump = OutputDevice(
                config.pump_pin,
                active_high=True,
                initial_value=False,
            )
            self.valve = OutputDevice(
                config.valve_pin,
                active_high=True,
                initial_value=False,
            )
            # MCP3008 provides ADC for analog soil sensors.
            self.sensors = [MCP3008(channel=ch)
                            for ch in config.moisture_channels]
        else:
            self.pump = None
            self.valve = None
            self.sensors = []

    def _read_state(self, device, fallback):
        if device is None:
            return fallback
        try:
            return device.value > 0
        except Exception:
            return fallback

    def status(self):
        return {
            "available": self.available,
            "pump_on": self._read_state(self.pump, self._pump_state),
            "valve_open": self._read_state(self.valve, self._valve_state),
            "moisture_channels": self.config.moisture_channels,
        }

    def set_pump(self, on: bool):
        if self.pump is None:
            self._pump_state = bool(on)
            return
        if on:
            self.pump.on()
        else:
            self.pump.off()

    def set_valve(self, open_value: bool):
        if self.valve is None:
            self._valve_state = bool(open_value)
            return
        if open_value:
            self.valve.on()
        else:
            self.valve.off()

    def water_for(self, seconds: int, zone: int = 0):
        _ = zone
        self.set_valve(True)
        self.set_pump(True)
        try:
            time.sleep(max(0, int(seconds)))
        finally:
            self.set_pump(False)
            self.set_valve(False)

    def read_moisture(self):
        readings = []
        for sensor in self.sensors:
            try:
                readings.append(round(sensor.value, 3))
            except Exception:
                readings.append(None)
        return readings

    def close(self):
        for device in (self.pump, self.valve):
            if device is not None:
                device.close()
        for sensor in self.sensors:
            if sensor is not None:
                sensor.close()
