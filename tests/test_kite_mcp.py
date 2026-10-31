import json

import pytest

from master_agent.data import kite, kite_mcp


class Reply:
    def __init__(self, text, content_type="application/json"):
        self.text, self.headers = text, {"Content-Type": content_type}

    def json(self):
        return json.loads(self.text)


def tool_reply(text, is_error=False, content_type="application/json"):
    body = json.dumps({"result": {"content": [{"type": "text", "text": text}], "isError": is_error}})
    return Reply(f"data: {body}\n" if "event-stream" in content_type else body, content_type)


@pytest.fixture
def session(monkeypatch, tmp_path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"session_id": "abc"}))
    monkeypatch.setattr(kite_mcp, "SESSION_FILE", f)
    monkeypatch.setattr(kite_mcp, "_tokens", {})
    return f


@pytest.mark.parametrize("tool", ["place_order", "modify_order", "cancel_order", "place_gtt_order",
                                  "modify_gtt_order", "delete_gtt_order", "anything_new"])
def test_order_tools_are_refused_without_a_network_call(monkeypatch, session, tool):
    def no_network(*a, **k):
        raise AssertionError("must not reach the server")
    monkeypatch.setattr(kite_mcp, "_post", no_network)
    with pytest.raises(PermissionError):
        kite_mcp.call(tool)


def test_event_stream_reply_is_decoded(monkeypatch, session):
    monkeypatch.setattr(kite_mcp, "_post", lambda *a: tool_reply('{"user_name": "A"}', content_type="text/event-stream"))
    assert kite_mcp.connected() == {"connected": True, "user": "A", "user_id": None}


def test_not_logged_in_is_reported(monkeypatch, session):
    monkeypatch.setattr(kite_mcp, "_post", lambda *a: tool_reply("Please log in first", is_error=True))
    assert kite_mcp.connected() == {"connected": False, "reason": "Please log in first"}


def test_no_session_means_no_network_call(monkeypatch, tmp_path):
    monkeypatch.setattr(kite_mcp, "SESSION_FILE", tmp_path / "none.json")
    def no_network(*a, **k):
        raise AssertionError("must not reach the server")
    monkeypatch.setattr(kite_mcp, "_post", no_network)
    assert kite_mcp.connected()["connected"] is False


def test_login_rejects_a_link_to_any_other_site(monkeypatch, session):
    monkeypatch.setattr(kite_mcp, "_new_session", lambda: "abc")
    monkeypatch.setattr(kite_mcp, "_post", lambda *a: tool_reply("[Login](https://evil.example/authorize?session_id=x)"))
    with pytest.raises(RuntimeError):
        kite_mcp.login_url()


def test_daily_builds_candles(monkeypatch, session):
    candle = {"date": "2026-10-30T00:00:00+05:30", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}

    def fake(body, sess):
        tool = body["params"]["name"]
        if tool == "search_instruments":
            return tool_reply(json.dumps({"data": [{"tradingsymbol": "INFYBEES", "exchange": "NSE", "instrument_token": 9},
                                                   {"tradingsymbol": "INFY", "exchange": "NSE", "instrument_token": 408065}]}))
        assert body["params"]["arguments"]["instrument_token"] == 408065
        return tool_reply(json.dumps([candle]))
    monkeypatch.setattr(kite_mcp, "_post", fake)
    df = kite_mcp.daily("INFY", "2026-10-29", "2026-10-30")
    assert df["close"].iloc[-1] == 1.5


def test_kite_uses_mcp_only_without_keys(monkeypatch):
    monkeypatch.delenv("KITE_API_KEY", raising=False)
    assert kite._provider() is kite_mcp
    monkeypatch.setenv("KITE_API_KEY", "k")
    assert kite._provider() is None
