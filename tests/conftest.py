import os
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def fake_env(monkeypatch, tmp_path):
    """Provide test env vars so config.load_config() never fails in tests."""
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR
