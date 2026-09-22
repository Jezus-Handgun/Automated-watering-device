import sqlite3
import click
from flask import current_app, g
from flask.cli import with_appcontext
from .storage import Store


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE_PATH"])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    Store(current_app.config["DATABASE_PATH"])


@click.command("init-db")
@with_appcontext
def init_db_command():
    init_db()
    click.echo("Database schema updated; existing data preserved.")
