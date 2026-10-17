"""Legacy tests stay offline; infrastructure integration opts in explicitly."""
import pytest


@pytest.fixture(autouse=True)
def offline_registry(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
