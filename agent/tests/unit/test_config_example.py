"""
Guard the shipped config template.

The README points operators at config.example.yaml; for a long time that file
did not exist at all. These tests make sure it exists, parses with the real
loader, and stays in step with the config schema.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from itbis_agent.config import Config

EXAMPLE = Path(__file__).resolve().parents[2] / "config.example.yaml"


def test_example_config_exists():
    assert EXAMPLE.is_file(), f"missing shipped template: {EXAMPLE}"


def test_example_config_parses():
    cfg = Config.from_yaml(EXAMPLE)
    assert cfg.agent.device_id
    assert cfg.server.base_url.startswith("https://")
    assert cfg.server.events_path == "/api/v1/ingestion/events"


def test_example_config_covers_every_setting():
    """Every field in the schema should be shown, or operators can't find it."""
    import yaml

    raw = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    sections = {
        "agent": Config.model_fields["agent"].annotation,
        "server": Config.model_fields["server"].annotation,
        "queue": Config.model_fields["queue"].annotation,
        "upload": Config.model_fields["upload"].annotation,
    }
    for name, schema in sections.items():
        documented = set(raw.get(name) or {})
        expected = set(schema.model_fields)
        missing = expected - documented
        assert not missing, f"config.example.yaml section {name!r} omits {sorted(missing)}"


def test_example_config_ships_tls_on_and_no_real_secret():
    cfg = Config.from_yaml(EXAMPLE)
    assert cfg.server.verify_tls is True, "template must not disable TLS verification"
    assert cfg.server.api_key == "REPLACE_ME", "template must not contain a real key"


@pytest.mark.parametrize(
    "collector",
    ["windows_security", "process", "usb", "removable_files", "downloads", "network"],
)
def test_example_enables_the_real_collectors(collector):
    cfg = Config.from_yaml(EXAMPLE)
    assert collector in cfg.agent.enabled_collectors
