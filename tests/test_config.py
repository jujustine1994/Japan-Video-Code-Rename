import json
from pathlib import Path

import pytest


def test_load_returns_default_when_no_file(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    cfg = config.load()
    assert cfg["target_dir"] == ""
    assert "cache_file" in cfg


def test_save_and_load_roundtrip(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    config.save({"target_dir": "D:\\Videos", "cache_file": "cache/c.json",
                 "processed_log": "p.json", "skipped_log": "s.json"})
    cfg = config.load()
    assert cfg["target_dir"] == "D:\\Videos"
