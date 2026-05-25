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


class WateringHardware:
    def __init__(self, config: HardwareConfig):
        self.config = config
        self.available = OutputDevice is not None and MCP3008 is not None
        self._pump_state = False
        self._valve_state = False

        if self.available:
            self.pump = OutputDevice(config.pump_pin, active_high=True, initial_value=False)
            self.valve = OutputDevice(config.valve_pin, active_high=True, initial_value=False)
            # MCP3008 provides ADC for analog soil sensors.
            self.sensors = [MCP3008(channel=ch) for ch in config.moisture_channels]
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
