import os

from app import create_app

app = create_app()


def _parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "y", "on"):
        return True
    if text in ("false", "0", "no", "n", "off"):
        return False
    return default


if __name__ == "__main__":
    debug = _parse_bool(os.environ.get("APP_DEBUG"), default=False)
    app.run(host="0.0.0.0", port=5000, debug=debug)
