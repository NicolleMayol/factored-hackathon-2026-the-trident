"""Precedencia de credenciales Databricks: token > service principal > perfil CLI (agent/adapters/dbx_auth.py)."""
import pytest
from agent.adapters import dbx_auth


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in ("DATABRICKS_TOKEN", "DATABRICKS_CLIENT_ID", "DATABRICKS_CLIENT_SECRET", "DATABRICKS_CONFIG_PROFILE", "DATABRICKS_HOST"):
        monkeypatch.delenv(k, raising=False)
    dbx_auth._cache.clear()


def test_token_first(monkeypatch):
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test")
    monkeypatch.setenv("DATABRICKS_CLIENT_ID", "x")
    assert dbx_auth.auth_headers() == {"Authorization": "Bearer dapi-test"}
    assert dbx_auth.mode() == "pat"


def test_profile_mode_name(monkeypatch):
    monkeypatch.setenv("DATABRICKS_CONFIG_PROFILE", "fh26")
    assert dbx_auth.mode() == "profile:fh26"


def test_profile_missing_gives_actionable_error(monkeypatch):
    monkeypatch.setenv("DATABRICKS_CONFIG_PROFILE", "no-existe-fh26")
    with pytest.raises(RuntimeError, match="databricks auth login"):
        dbx_auth.auth_headers()


def test_host_from_env(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "https://adb-1.azuredatabricks.net/")
    assert dbx_auth.host() == "https://adb-1.azuredatabricks.net"
