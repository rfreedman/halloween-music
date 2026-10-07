"""Background Bluetooth connection watchdog."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

from halloween_music.bluetooth.base import BluetoothAdapter, BluetoothStatus
from halloween_music.config import ConfigStore
from halloween_music.player import Player
from halloween_music.schedule_util import in_schedule_window

logger = logging.getLogger(__name__)


class BluetoothMonitor:
    def __init__(
        self,
        config: ConfigStore,
        adapter: BluetoothAdapter,
        player: Player,
    ) -> None:
        self.config = config
        self.adapter = adapter
        self.player = player
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._reconnecting = False
        self._last_error: str | None = None
        self._next_attempt = 0.0
        self._force_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="bt-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._force_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def request_reconnect(self) -> None:
        with self._lock:
            self._next_attempt = 0.0
            self._last_error = None
        self._force_event.set()

    def status(self) -> BluetoothStatus:
        cfg = self.config.snapshot()
        address = cfg.bluetooth.device_address
        connected = False
        try:
            connected = self.adapter.is_connected(address)
        except Exception as exc:
            logger.debug("BT status check failed: %s", exc)
        with self._lock:
            return BluetoothStatus(
                connected=connected,
                address=address,
                name=cfg.bluetooth.device_name,
                reconnecting=self._reconnecting,
                last_error=self._last_error,
            )

    def connect_now(self, address: str | None = None) -> None:
        cfg = self.config.snapshot()
        target = address or cfg.bluetooth.device_address
        with self._lock:
            self._reconnecting = True
            self._last_error = None
        try:
            if not self.adapter.is_connected(target):
                logger.info("Connecting Bluetooth device %s", target)
                self.adapter.connect(target)
            try:
                self.adapter.ensure_audio_route(target, cfg.bluetooth.device_name)
            except Exception as route_exc:
                logger.warning("Audio route after connect: %s", route_exc)
            with self._lock:
                self._last_error = None
                self._next_attempt = 0.0
        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
            logger.warning("Bluetooth connect failed: %s", exc)
            raise
        finally:
            with self._lock:
                self._reconnecting = False

    def switch_address(self, old_address: str | None, new_address: str) -> None:
        if old_address and old_address.upper() != new_address.upper():
            try:
                if self.adapter.is_connected(old_address):
                    self.adapter.disconnect(old_address)
            except Exception as exc:
                logger.warning("Failed disconnecting old BT device %s: %s", old_address, exc)
        self.request_reconnect()
        cfg = self.config.snapshot()
        if in_schedule_window(datetime.now(), cfg.schedule.start, cfg.schedule.stop):
            try:
                self.connect_now(new_address)
            except Exception:
                pass

    def _run(self) -> None:
        while not self._stop.is_set():
            cfg = self.config.snapshot()
            poll = max(5, int(cfg.bluetooth.poll_seconds))
            backoff = max(5, int(cfg.bluetooth.reconnect_backoff_seconds))
            active = in_schedule_window(
                datetime.now(), cfg.schedule.start, cfg.schedule.stop
            )

            if active:
                address = cfg.bluetooth.device_address
                try:
                    connected = self.adapter.is_connected(address)
                except Exception as exc:
                    connected = False
                    with self._lock:
                        self._last_error = str(exc)

                if not connected:
                    now = time.time()
                    with self._lock:
                        due = now >= self._next_attempt
                    if due:
                        try:
                            self.connect_now(address)
                            if self.player.is_playing:
                                try:
                                    device = self.adapter.ensure_audio_route(
                                        address, cfg.bluetooth.device_name
                                    )
                                    self.player.restart_if_playing(audio_device=device)
                                except Exception as exc:
                                    logger.warning("Player restart after BT reconnect: %s", exc)
                        except Exception:
                            with self._lock:
                                self._next_attempt = time.time() + backoff
                else:
                    with self._lock:
                        self._last_error = None

            self._force_event.wait(timeout=poll)
            self._force_event.clear()
