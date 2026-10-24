import pytest

from scale2zwift.sync import Syncer
from scale2zwift.web import create_app


@pytest.fixture
def app(store, garmin, monkeypatch):
    monkeypatch.setenv("UI_PASSWORD", "secret")
    return create_app(store, garmin, Syncer(store, garmin))


AUTH = {"Authorization": "Basic YWRtaW46c2VjcmV0"}  # admin:secret


def test_requires_password(app):
    c = app.test_client()
    assert c.get("/").status_code == 401
    assert c.get("/", headers=AUTH).status_code == 200
    assert c.get("/healthz").status_code == 200


def test_page_renders_disconnected(app):
    html = app.test_client().get("/", headers=AUTH).get_data(as_text=True)
    assert "Not connected" in html and "Connect both accounts" in html


def test_cross_site_post_blocked(app):
    c = app.test_client()
    r = c.post("/settings", data={"interval_hours": "2"}, headers={**AUTH, "Origin": "https://evil.example"})
    assert r.status_code == 403
    r = c.post("/settings", data={"interval_hours": "2"}, headers={**AUTH, "Origin": "http://localhost"})
    assert r.status_code == 302


def test_settings_validation(app, store):
    c = app.test_client()
    c.post("/settings", data={"interval_hours": "999"}, headers=AUTH)
    assert "interval_hours" not in store.state.load()
    c.post("/settings", data={"interval_hours": "2"}, headers=AUTH)
    assert store.state.load()["interval_hours"] == 2.0


def test_secrets_file_is_private(store):
    store.secrets.save({"zwift_password": "x"})
    assert (store.secrets.path.stat().st_mode & 0o777) == 0o600
