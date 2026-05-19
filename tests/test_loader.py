"""Tests for loader.py: config merge logic and _system injection."""

from pathlib import Path

import pytest
import yaml

import loader
from loader import _deep_merge


class TestDeepMerge:
    def test_three_level_merge(self):
        base   = {"a": 1, "b": 2}
        shared = {"b": 3, "c": 4}
        server = {"c": 5, "d": 6}
        merged = _deep_merge(_deep_merge(base, shared), server)
        assert merged == {"a": 1, "b": 3, "c": 5, "d": 6}

    def test_list_replacement(self):
        base   = {"recipients": ["a@x.com"]}
        shared = {"recipients": ["b@x.com", "c@x.com"]}
        merged = _deep_merge(base, shared)
        assert merged["recipients"] == ["b@x.com", "c@x.com"]
        assert len(merged["recipients"]) == 2

    def test_nested_dict_merged(self):
        base   = {"smtp": {"host": "mail.example.com", "port": 25}}
        override = {"smtp": {"port": 587}}
        merged = _deep_merge(base, override)
        assert merged["smtp"]["host"] == "mail.example.com"
        assert merged["smtp"]["port"] == 587


class TestLoadConfig:
    def test_system_injected_in_all_slices(self, tmp_path, monkeypatch):
        base_dir = tmp_path / "base"
        base_dir.mkdir()
        (base_dir / "general.yaml").write_text("cron_schedule: '0 8 * * *'\n")
        (base_dir / "cpu.yaml").write_text("load_multiplier: 1.5\n")

        monkeypatch.setattr(loader, "CONFIGS_DIR", tmp_path)
        config = loader.load_config()

        for key, value in config.items():
            if not key.startswith("_"):
                assert "_system" in value, f"_system missing from config[{key!r}]"

    def test_system_not_in_yaml(self):
        configs_base = Path("configs/base")
        for yaml_file in sorted(configs_base.glob("*.yaml")):
            content = yaml_file.read_text()
            assert "_system" not in content, f"_system found in {yaml_file.name}"
