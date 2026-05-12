import os
import pytest

from vidistill.config import load_config, Config


def test_load_config_returns_config_with_api_key(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test-123")
    config = load_config()
    assert isinstance(config, Config)
    assert config.dashscope_api_key == "sk-test-123"


def test_load_config_uses_default_values(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test-123")
    config = load_config()
    assert config.qwen_model == "qwen-plus"
    assert config.paraformer_model == "paraformer-v2"
    assert config.max_video_duration_seconds == 1800
    assert config.pipeline_timeout_seconds == 1800
    assert config.min_free_disk_mb == 500
    assert config.dashscope_compatible_base_url.startswith("https://dashscope.aliyuncs.com")


def test_load_config_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DASHSCOPE_API_KEY"):
        load_config()
