"""Production server.  Run:  python -m web.serve

Serves on 127.0.0.1:8000 for Caddy, which adds HTTPS in front (see deploy/). Refuses to start
without an owner password, so the robot and Zerodha controls are never left open to visitors.
"""
from __future__ import annotations

import os
import sys
import threading

from waitress import serve
from werkzeug.middleware.proxy_fix import ProxyFix

from web import app as webapp


def main() -> None:
    missing = [k for k in ("OWNER_PASSWORD_HASH", "SECRET_KEY") if not os.environ.get(k)]
    if missing:
        sys.exit(f"Refusing to start: {', '.join(missing)} not set. Run:  python -m web.set_password")
    app = webapp.app
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)   # trust exactly one proxy: Caddy
    threading.Thread(target=webapp._robot_loop, daemon=True).start()
    serve(app, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")), threads=8)


if __name__ == "__main__":
    main()
