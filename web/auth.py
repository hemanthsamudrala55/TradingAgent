"""Owner login and the visitor view.

With OWNER_PASSWORD_HASH unset (running on your own PC) everyone is the owner. On a server,
web/serve.py refuses to start without it. Visitors without the password see only the Stocks
screen, with Yahoo prices: never the robot, its trades or anything from Zerodha, whose terms
do not allow showing its data to others.
"""
from __future__ import annotations

import os
import time
from datetime import timedelta
from urllib.parse import urlparse

from flask import Flask, jsonify, redirect, render_template, request, session
from werkzeug.security import check_password_hash

PUBLIC = {"simple", "static", "api_chart", "api_search", "api_picks", "status", "login", "logout"}
MAX_FAILURES, WINDOW = 5, 15 * 60
_failures: dict[str, list[float]] = {}


def enabled() -> bool:
    return bool(os.environ.get("OWNER_PASSWORD_HASH"))


def is_owner() -> bool:
    return not enabled() or session.get("owner") is True


def _same_origin() -> bool:
    origin = request.headers.get("Origin")
    return bool(origin) and urlparse(origin).netloc == request.host


def _guard():
    if enabled() and request.method not in ("GET", "HEAD", "OPTIONS") and not _same_origin():
        return jsonify({"error": "Request refused: it did not come from this site"}), 403
    if is_owner() or request.endpoint in PUBLIC:
        return None
    if request.path.startswith(("/api/", "/kite/")):
        return jsonify({"error": "Owner login needed"}), 401
    return redirect("/login")


def _blocked(ip: str) -> bool:
    now = time.time()
    _failures[ip] = [t for t in _failures.get(ip, []) if now - t < WINDOW]
    return len(_failures[ip]) >= MAX_FAILURES


def login():
    if request.method == "GET":
        return render_template("login.html", error=None)
    ip = request.remote_addr or "?"
    if _blocked(ip):
        return render_template("login.html", error="Too many wrong tries. Wait 15 minutes."), 429
    if enabled() and check_password_hash(os.environ["OWNER_PASSWORD_HASH"], request.form.get("password", "")):
        _failures.pop(ip, None)
        session.clear()
        session["owner"] = True
        session.permanent = True
        return redirect("/")
    _failures.setdefault(ip, []).append(time.time())
    return render_template("login.html", error="Wrong password."), 401


def logout():
    session.clear()
    return redirect("/")


def install(app: Flask) -> None:
    app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=enabled() and os.environ.get("COOKIE_SECURE", "1") == "1",
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=12))
    app.before_request(_guard)
    app.add_url_rule("/login", "login", login, methods=["GET", "POST"])
    app.add_url_rule("/logout", "logout", logout, methods=["POST"])
