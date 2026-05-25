import os


class Config:
    DATABASE_PATH = os.environ.get("DATABASE_PATH", "instance/watering.db")
    PUMP_PIN = int(os.environ.get("PUMP_PIN", "17"))
    VALVE_PIN = int(os.environ.get("VALVE_PIN", "27"))
    MOISTURE_CHANNELS = os.environ.get("MOISTURE_CHANNELS", "0,1,2")
