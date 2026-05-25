import os
from flask import Flask

from .config import Config
from .db import close_db, init_db_command
from .routes import api_bp


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    os.makedirs(app.instance_path, exist_ok=True)

    app.register_blueprint(api_bp)
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)

    return app
