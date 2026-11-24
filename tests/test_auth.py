import pandas as pd
import pytest
from werkzeug.security import generate_password_hash

from web import app as webapp
from web import auth

PASSWORD = "correct horse battery"
HOST = "http://localhost"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(webapp.kite, "connected", lambda: {"connected": False})
    monkeypatch.setattr(webapp.kite, "orders_ready", lambda: False)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", generate_password_hash(PASSWORD))
    monkeypatch.setattr(auth, "_failures", {})
    webapp.app.config["TESTING"] = True
    return webapp.app.test_client()


def login(c, pw=PASSWORD):
    return c.post("/login", data={"password": pw}, headers={"Origin": HOST})


@pytest.mark.parametrize("path", ["/api/robot", "/api/portfolio", "/kite/login", "/api/live"])
def test_visitor_blocked_from_owner_api(client, path):
    assert client.get(path).status_code == 401


def test_visitor_sent_to_login_from_advanced(client):
    r = client.get("/advanced")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")


def test_visitor_sees_main_page_and_minimal_status(client):
    assert client.get("/").status_code == 200
    s = client.get("/api/status").get_json()
    assert s["owner"] is False and "kite" not in s and "orders_ready" not in s


def test_visitor_cannot_change_robot(client):
    r = client.post("/api/robot/settings", json={"mode": "practice"}, headers={"Origin": HOST})
    assert r.status_code == 401


def test_visitor_prices_always_yahoo(client, monkeypatch):
    monkeypatch.setattr(webapp, "default_source", lambda: "kite")
    asked = []
    fetch = lambda sym, src: asked.append(src) or pd.DataFrame()   # noqa: E731
    with webapp.app.test_request_context("/api/chart"):
        webapp._prices("TCS", fetch)
    assert asked == ["yahoo"]


def test_owner_login_and_logout(client):
    r = login(client)
    assert r.status_code == 302
    assert client.get("/api/status").get_json()["owner"] is True
    assert client.get("/advanced").status_code == 200
    client.post("/logout", headers={"Origin": HOST})
    assert client.get("/api/status").get_json()["owner"] is False


def test_wrong_password_and_lockout(client):
    for _ in range(auth.MAX_FAILURES):
        assert login(client, "wrong password!").status_code == 401
    assert login(client).status_code == 429          # even the right password waits now


def test_post_from_other_site_refused(client):
    login(client)
    r = client.post("/api/robot/check", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert client.post("/api/robot/check").status_code == 403   # no Origin at all


def test_no_password_means_local_owner(monkeypatch):
    monkeypatch.delenv("OWNER_PASSWORD_HASH", raising=False)
    c = webapp.app.test_client()
    assert c.get("/api/status").get_json()["owner"] is True
