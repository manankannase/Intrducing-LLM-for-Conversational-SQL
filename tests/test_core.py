import io
import json

import pytest

import core


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.query = None
        self.closed = False

    def execute(self, query, params=None):
        self.query = query

    def fetchmany(self, count):
        return self.rows[:count]

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, rows):
        self.cursor_instance = FakeCursor(rows)

    def cursor(self, **_kwargs):
        return self.cursor_instance


def test_call_groq_requires_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(core.ConfigurationError, match="GROQ_API_KEY"):
        core.call_groq([])


def test_call_groq_parses_response(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    body = json.dumps({"choices": [{"message": {"content": " SELECT 1 "}}]}).encode()
    monkeypatch.setattr(core, "urlopen", lambda *_args, **_kwargs: FakeResponse(body))
    assert core.call_groq([]) == "SELECT 1"


def test_history_keeps_latest_ten_messages():
    history = [{"role": "user", "content": str(i)} for i in range(12)]
    text = core.history_text(history)
    assert "user: 0" not in text
    assert "user: 11" in text


def test_execute_query_revalidates_and_limits_results():
    connection = FakeConnection([{"value": i} for i in range(120)])
    rows = core.execute_query(connection, "SELECT value FROM sample")
    assert len(rows) == 100
    assert "LIMIT 100" in connection.cursor_instance.query.upper()
    assert connection.cursor_instance.closed


def test_invalid_port_is_rejected_before_connection():
    with pytest.raises(core.ConfigurationError, match="port"):
        core.connect_database(host="localhost", port="invalid", user="u", password="p", database="d")
