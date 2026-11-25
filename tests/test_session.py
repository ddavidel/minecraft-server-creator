"""Session marker, app_close sent once and queued on disk, shutdown blocker."""

from __future__ import annotations

import json
from unittest import mock

import pytest

from mcsc_gui import telemetry
from mcsc_gui.core import session


@pytest.fixture(autouse=True)
def _reset_close_flag():
    session._reset_for_tests()  # pylint: disable=protected-access
    yield
    session._reset_for_tests()  # pylint: disable=protected-access


@pytest.fixture
def client(tmp_path):
    with mock.patch.object(telemetry.TelemetryClient, "_send", return_value=False):
        yield telemetry.TelemetryClient("http://telemetry.invalid", tmp_path / "telemetry")


def pending(client):
    return [json.loads(f.read_text(encoding="utf-8")) for f in client._load_pending()]  # pylint: disable=protected-access


# ------------------------------------------------------------------ marker


def test_marker_detects_an_unclean_previous_session(tmp_path):
    marker = str(tmp_path / "data" / "session.lock")
    assert session.begin(marker) is False  # first run
    assert session.begin(marker) is True  # never ended: killed
    session.end(marker)
    assert session.begin(marker) is False
    session.end(marker)
    session.end(marker)  # idempotent


# ------------------------------------------------------------------ telemetry


def test_durable_event_is_queued_when_the_send_fails(client):
    client.send_event_durable("app_close", {"reason": "session_end"})
    [payload] = pending(client)
    assert payload["event_name"] == "app_close"
    assert payload["details"] == {"reason": "session_end", "delayed": True}


def test_durable_event_is_unqueued_once_sent(client):
    sent = []

    def fake_send(payload, timeout=5):
        sent.append((payload, timeout))
        # Already on disk while the request runs: survives a kill meanwhile
        assert len(client._load_pending()) == 1  # pylint: disable=protected-access
        return True

    with mock.patch.object(client, "_send", fake_send):
        client.send_event_durable("app_close", {"reason": "quit"}, timeout=1.5)
    assert pending(client) == []
    [(payload, timeout)] = sent
    assert payload["details"] == {"reason": "quit"}  # the live copy isn't "delayed"
    assert timeout == 1.5


def test_durable_event_validates_like_send_event(client):
    with pytest.raises(ValueError):
        client.send_event_durable("not_an_event")
    assert pending(client) == []


def test_app_close_is_sent_once(client):
    with mock.patch.object(session, "get_telemetry_client", return_value=client):
        assert session.send_app_close(session.REASON_SESSION_END) is True
        assert session.send_app_close(session.REASON_QUIT) is False
    [payload] = pending(client)
    assert payload["details"]["reason"] == "session_end"


def test_app_close_never_raises():
    broken = mock.Mock(send_event_durable=mock.Mock(side_effect=OSError("disk full")))
    with mock.patch.object(session, "get_telemetry_client", return_value=broken):
        assert session.send_app_close(session.REASON_QUIT) is True


def test_unclean_close_is_marked_delayed(client):
    with mock.patch.object(session, "get_telemetry_client", return_value=client):
        session.send_unclean_close()
    [payload] = pending(client)
    assert payload["details"] == {"reason": "unclean", "delayed": True}


# ------------------------------------------------------------------ blocker


def test_blocker_does_nothing_where_unsupported():
    blocker = session.ShutdownBlocker()
    blocker.supported = False
    blocker.block(123, "reason")
    assert not blocker.active
    blocker.release()


def test_blocker_creates_and_destroys_the_reason():
    user32 = mock.Mock()
    user32.ShutdownBlockReasonCreate.return_value = 1
    windll = mock.Mock(user32=user32)
    blocker = session.ShutdownBlocker()
    blocker.supported = True
    with mock.patch("ctypes.windll", windll, create=True):
        blocker.block(42, "Stopping")
        blocker.block(42, "Stopping")  # unchanged: no new call
        assert blocker.active
        assert user32.ShutdownBlockReasonCreate.call_count == 1
        blocker.release()
        blocker.release()
    assert not blocker.active
    assert user32.ShutdownBlockReasonDestroy.call_count == 1
