import signal

from app import close_app, create_app, start_services

app = create_app()


def _shutdown(signum, frame):
    raise SystemExit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    try:
        start_services(app)
        # A reloader would create another process owning the same physical pins.
        app.run(host="0.0.0.0", port=5000, debug=False,
                use_reloader=False, threaded=True)
    finally:
        close_app(app)
