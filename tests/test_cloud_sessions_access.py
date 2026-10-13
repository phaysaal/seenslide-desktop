"""CloudSessionsClient.update_session_access: payload, auth header, and
error mapping for the owner-only PUT /api/cloud/session/{id}/access route."""
from unittest.mock import patch, MagicMock

import core.cloud_sessions as cs


def _client():
    return cs.CloudSessionsClient(api_url="https://cloud.example", token="tok-123")


def _resp(status, payload=None, text=""):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload if payload is not None else {}
    r.text = text
    return r


def test_password_protected_sends_password_and_bearer():
    with patch.object(cs.requests, "put", return_value=_resp(200, {"access_type": "password_protected"})) as put:
        out = _client().update_session_access("ABC-1234", "password_protected", "hunter22")
    assert out == {"ok": True, "access_type": "password_protected"}
    args, kwargs = put.call_args
    assert args[0] == "https://cloud.example/api/cloud/session/ABC-1234/access"
    assert kwargs["json"] == {"access_type": "password_protected", "password": "hunter22"}
    assert kwargs["headers"]["Authorization"] == "Bearer tok-123"


def test_public_omits_password():
    with patch.object(cs.requests, "put", return_value=_resp(200)) as put:
        out = _client().update_session_access("ABC-1234", "public", "ignored")
    assert out["ok"] is True
    assert put.call_args.kwargs["json"] == {"access_type": "public"}


def test_password_required_locally():
    with patch.object(cs.requests, "put") as put:
        out = _client().update_session_access("ABC-1234", "password_protected", "  ")
    assert out["ok"] is False and "password" in out["error"].lower()
    put.assert_not_called()


def test_unknown_access_type_rejected_locally():
    with patch.object(cs.requests, "put") as put:
        out = _client().update_session_access("ABC-1234", "secret")
    assert out["ok"] is False
    put.assert_not_called()


def test_not_owner_maps_403():
    with patch.object(cs.requests, "put", return_value=_resp(403, {"detail": "Only the session owner can change access"})):
        out = _client().update_session_access("ABC-1234", "private")
    assert out["ok"] is False and "owner" in out["error"].lower()


def test_weak_password_surfaces_server_detail():
    with patch.object(cs.requests, "put", return_value=_resp(400, {"detail": "Password must be at least 6 characters long"})):
        out = _client().update_session_access("ABC-1234", "password_protected", "abc")
    assert out["ok"] is False and "6 characters" in out["error"]


def test_network_error_does_not_raise():
    with patch.object(cs.requests, "put", side_effect=cs.requests.RequestException("boom")):
        out = _client().update_session_access("ABC-1234", "public")
    assert out["ok"] is False and "network" in out["error"].lower()


def test_unconfigured_client():
    c = cs.CloudSessionsClient(api_url="", token="tok")
    out = c.update_session_access("ABC-1234", "public")
    assert out["ok"] is False
