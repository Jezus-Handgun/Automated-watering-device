import atexit
import os
from pathlib import Path
import threading

from flask import Flask

from .config import Config
from .db import close_db, init_db_command
from .hardware.gpio_controller import build_hardware_config
from .routes import api_bp
from .storage import Store


def close_app(app):
    with app.extensions["controller_lock"]:
        app.extensions["controller_closed"] = True
        controller = app.extensions.get("controller")
        if controller is not None:
            controller.close()


def create_app(test_config=None):
    frontend = Path(__file__).resolve().parents[2] / "frontend"
    app = Flask(__name__, instance_relative_config=True,
                static_folder=str(frontend), static_url_path="")
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    app.extensions["hardware_config"] = build_hardware_config(app.config)
    timeout = app.config["MANUAL_TIMEOUT_SECONDS"]
    if type(timeout) is not int or not 1 <= timeout <= 600:
        raise ValueError(
            "MANUAL_TIMEOUT_SECONDS musi być liczbą całkowitą od 1 do 600.")
    app.extensions["controller_lock"] = threading.Lock()

    os.makedirs(app.instance_path, exist_ok=True)
    db_path = app.config.get("DATABASE_PATH", "instance/watering.db")
    if not os.path.isabs(db_path):
        for prefix in ("instance" + os.sep, "instance/"):
            if db_path.startswith(prefix):
                db_path = db_path[len(prefix):]
                break
        db_path = os.path.join(app.instance_path, db_path)
    app.config["DATABASE_PATH"] = db_path
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    app.extensions["store"] = Store(db_path)

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    app.register_blueprint(api_bp)
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    atexit.register(close_app, app)
    return app


def start_services(app):
    """Start sampling at process startup, independent of browser traffic."""
    from .routes import _get_controller
    with app.app_context():
        _get_controller().start_sampling()
