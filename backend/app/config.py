import os


class Config:
    DATABASE_PATH = os.environ.get("DATABASE_PATH", "instance/watering.db")
    PUMP_PIN = os.environ.get("PUMP_PIN", "17")
    VALVE_PIN = os.environ.get("VALVE_PIN", "27")
    MOISTURE_CHANNELS = os.environ.get("MOISTURE_CHANNELS", "0,1,2")
    HARDWARE_MODE = os.environ.get("HARDWARE_MODE", "real")
    MANUAL_TIMEOUT_SECONDS = int(
        os.environ.get("MANUAL_TIMEOUT_SECONDS", "60"))
    FLOW_PIN = os.environ.get("FLOW_PIN")
    FLOW_PULL_UP = os.environ.get("FLOW_PULL_UP", "1")
