"""
Console control events must stop the agent on Windows.

Regression: AgentRuntime.start() parked the main thread in an untimed
`threading.Event.wait()`. On Windows that wait can't be interrupted, and a
Python signal handler only runs once the main thread is back in bytecode — so
the SIGINT handler never ran, Ctrl+C was ignored, and the agent could only be
killed.

The test drives a real agent process. It sends Ctrl+Break rather than Ctrl+C
because Windows does not deliver CTRL_C_EVENT to a separate process group, and
sending it to our own console would interrupt the test run itself. Both
signals reach the same handler and depend on the same interruptible wait.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import threading
import time

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows console control events"
)


def _write_config(tmp_path) -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        textwrap.dedent(
            f"""
            agent:
              device_id: "SIGNAL-TEST"
              device_name: "Signal Test"
              poll_interval_seconds: 0.5
              enabled_collectors: ["mock"]
            server:
              base_url: "http://127.0.0.1:9"
              api_key: "itbis_ag_signal_notreal"
              verify_tls: false
              timeout_seconds: 1.0
            queue:
              db_path: "{(tmp_path / 'agent.db').as_posix()}"
            logging:
              level: "INFO"
              json: true
            """
        ),
        encoding="utf-8",
    )
    return str(cfg)


def test_ctrl_break_stops_the_agent_gracefully(tmp_path):
    proc = subprocess.Popen(
        [sys.executable, "-m", "itbis_agent", "--config", _write_config(tmp_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    lines: list[str] = []
    reader = threading.Thread(
        target=lambda: lines.extend(iter(proc.stderr.readline, "")), daemon=True
    )
    reader.start()

    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not any(
            "agent.running" in line for line in lines
        ):
            if proc.poll() is not None:
                pytest.fail(f"agent exited during startup: {''.join(lines)}")
            time.sleep(0.1)
        assert any("agent.running" in line for line in lines), (
            f"agent never reported agent.running: {''.join(lines)}"
        )

        os.kill(proc.pid, signal.CTRL_BREAK_EVENT)

        try:
            returncode = proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pytest.fail("agent ignored Ctrl+Break and kept running")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        reader.join(5)

    output = "".join(lines)
    # A graceful stop: the handler ran, shutdown completed, clean exit code.
    # Without the handler Windows terminates the process with 0xC000013A.
    assert "agent.signal" in output, output
    assert "agent.stopping" in output, output
    assert returncode == 0, f"exit code {returncode}"
