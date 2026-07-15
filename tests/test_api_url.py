"""api_url TLS enforcement: an http:// config value must never silently
downgrade the bearer token / slides / audio to cleartext."""
import core.identity as identity


def _resolve_with(monkeypatch, tmp_path, url):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"cloud:\n  api_url: {url}\n")
    monkeypatch.setattr(identity, "CONFIG_PATHS", [cfg])
    return identity._resolve_api_url()


def test_https_url_accepted(monkeypatch, tmp_path):
    assert _resolve_with(monkeypatch, tmp_path,
                         "https://example.com/") == "https://example.com"


def test_http_url_rejected_falls_back(monkeypatch, tmp_path):
    assert _resolve_with(monkeypatch, tmp_path,
                         "http://evil.example.com") == "https://seenslide.com"


def test_http_localhost_allowed_for_dev(monkeypatch, tmp_path):
    assert _resolve_with(monkeypatch, tmp_path,
                         "http://localhost:8000") == "http://localhost:8000"
    assert _resolve_with(monkeypatch, tmp_path,
                         "http://127.0.0.1:8000") == "http://127.0.0.1:8000"


def test_default_when_no_config(monkeypatch):
    monkeypatch.setattr(identity, "CONFIG_PATHS", [])
    assert identity._resolve_api_url() == "https://seenslide.com"
