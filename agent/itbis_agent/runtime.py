"""
ITBIS Endpoint Agent — Runtime orchestrator

Glues collectors → normaliser → queue → uploader together.
"""
from __future__ import annotations

import signal
import threading
from collections.abc import Iterable

import structlog

from itbis_agent.collectors.base import Collector
from itbis_agent.collectors.mock import MockCollector
from itbis_agent.collectors.process import ProcessCollector
from itbis_agent.collectors.usb import USBCollector
from itbis_agent.collectors.windows_security import WindowsSecurityCollector
from itbis_agent.config import Config
from itbis_agent.normalizer import Normaliser
from itbis_agent.queue import PersistentQueue
from itbis_agent.uploader import Uploader

log = structlog.get_logger(__name__)

COLLECTOR_REGISTRY: dict[str, type[Collector]] = {
    "windows_security": WindowsSecurityCollector,
    "process": ProcessCollector,
    "usb": USBCollector,
    "mock": MockCollector,
}


class AgentRuntime:
    """
    Long-running orchestrator.

    Lifecycle:
        runtime = AgentRuntime(config)
        runtime.start()     # blocks until stop() is called
        ...
        runtime.stop()
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self.agent_id = config.agent.device_id
        self._stop = threading.Event()
        self._collector_threads: list[tuple[Collector, threading.Thread]] = []
        self._uploader_thread: threading.Thread | None = None
        self._normaliser: Normaliser | None = None
        self._queue: PersistentQueue | None = None
        self._uploader: Uploader | None = None

    # ─── Public API ─────────────────────────────────────────

    def start(self) -> None:
        log.info(
            "agent.start",
            agent_id=self.agent_id,
            source_dataset=self.config.agent.source_dataset,
        )

        self._queue = PersistentQueue(self.config.queue, agent_id=self.agent_id)
        self._normaliser = Normaliser(self.config.agent)
        self._uploader = Uploader(
            server=self.config.server,
            upload=self.config.upload,
            queue=self._queue,
            agent_id=self.agent_id,
        )

        self._uploader.start()
        self._start_collectors(self.config.agent.enabled_collectors)
        self._start_uploader_thread()
        self._install_signal_handlers()

        # Block on the stop event (signal handler / external stop() flips it)
        self._stop.wait()
        log.info("agent.stopping")
        self._shutdown()

    def stop(self) -> None:
        self._stop.set()

    # ─── Collectors ─────────────────────────────────────────

    def _start_collectors(self, names: Iterable[str]) -> None:
        for name in names:
            cls = COLLECTOR_REGISTRY.get(name)
            if cls is None:
                log.warning("agent.unknown_collector", name=name)
                continue
            coll = cls(poll_interval_seconds=self.config.agent.poll_interval_seconds)
            coll.start()
            thread = threading.Thread(
                target=self._collector_loop,
                args=(coll,),
                name=f"collector-{name}",
                daemon=True,
            )
            thread.start()
            self._collector_threads.append((coll, thread))

    def _collector_loop(self, collector: Collector) -> None:
        try:
            for raw in collector.collect():
                if self._stop.is_set():
                    break
                if not raw:
                    continue
                self._handle_raw(raw)
        except Exception:  # noqa: BLE001
            log.exception("collector.crashed", name=collector.name)

    def _handle_raw(self, raw: dict) -> None:
        assert self._normaliser is not None
        assert self._queue is not None
        event = self._normaliser.normalise(raw)
        if event is None:
            return
        inserted = self._queue.enqueue(event)
        if not inserted:
            log.debug("queue.duplicate", idem=event.idempotency_key())

    # ─── Uploader thread ────────────────────────────────────

    def _start_uploader_thread(self) -> None:
        assert self._uploader is not None
        self._uploader_thread = threading.Thread(
            target=self._uploader_loop,
            name="uploader",
            daemon=True,
        )
        self._uploader_thread.start()

    def _uploader_loop(self) -> None:
        assert self._uploader is not None
        while not self._stop.is_set():
            try:
                stats = self._uploader.tick()
            except Exception:  # noqa: BLE001
                log.exception("uploader.tick_error")
                stats = {"sent": 0, "duplicates": 0, "rejected": 0, "retries": 0}
            if stats.get("sent") or stats.get("retries"):
                log.info("uploader.stats", **stats)
            # Sleep flush_interval OR until stop, whichever comes first
            self._stop.wait(timeout=self.config.upload.flush_interval_seconds)

    # ─── Shutdown ───────────────────────────────────────────

    def _shutdown(self) -> None:
        for coll, _ in self._collector_threads:
            try:
                coll.stop()
            except Exception:  # noqa: BLE001
                log.exception("collector.stop_error", name=coll.name)
        for _, t in self._collector_threads:
            t.join(timeout=5)
        if self._uploader is not None:
            self._uploader.stop()
        if self._uploader_thread is not None:
            self._uploader_thread.join(timeout=5)
        if self._queue is not None:
            self._queue.close()
        log.info("agent.stopped")

    # ─── Signal handling ────────────────────────────────────

    def _install_signal_handlers(self) -> None:
        def _handler(signum, frame):  # noqa: ARG001
            log.info("agent.signal", signum=signum)
            self.stop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _handler)
            except (ValueError, OSError):
                # Not in main thread or unsupported platform
                pass
