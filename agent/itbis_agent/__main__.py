"""ITBIS Endpoint Agent — CLI entrypoint."""
from __future__ import annotations

import argparse
import sys

import structlog

from itbis_agent.config import Config
from itbis_agent.logging_config import configure_logging
from itbis_agent.runtime import AgentRuntime

log = structlog.get_logger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="itbis-agent",
        description="ITBIS Windows Endpoint Agent",
    )
    p.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to a YAML config file.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.config:
            config = Config.from_yaml(args.config)
        else:
            config = Config.from_env()
    except Exception as exc:  # noqa: BLE001
        print(f"itbis-agent: failed to load configuration: {exc}", file=sys.stderr)
        return 2

    configure_logging(config.logging)

    runtime = AgentRuntime(config)
    try:
        runtime.start()
    except KeyboardInterrupt:
        runtime.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
