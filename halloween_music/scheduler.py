"""Daily start/stop playback scheduler."""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Literal

from halloween_music.bluetooth.monitor import BluetoothMonitor
from halloween_music.config import ConfigStore
from halloween_music.player import Player
from halloween_music.playlist import parse_m3u
from halloween_music.schedule_util import in_schedule_window

logger = logging.getLogger(__name__)

ManualOverride = Literal["play", "stop"] | None


class Scheduler:
    def __init__(
        self,
        config: ConfigStore,
        player: Player,
        bt_monitor: BluetoothMonitor,
        tick_seconds: float = 15.0,
    ) -> None:
        self.config = config
        self.player = player
        self.bt_monitor = bt_monitor
        self.tick_seconds = tick_seconds
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._override: ManualOverride = None
        self._was_in_window: bool | None = None
        self._audio_error: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def wake(self) -> None:
        """Force an immediate schedule evaluation (e.g. after config change)."""
        self._wake.set()

    def evaluate_now(self) -> None:
        with self._lock:
            self._tick()

    @property
    def manual_override(self) -> ManualOverride:
        with self._lock:
            return self._override

    @property
    def audio_error(self) -> str | None:
        with self._lock:
            return self._audio_error

    def manual_play(self) -> None:
        with self._lock:
            self._override = "play"
        self.wake()
        self.evaluate_now()

    def manual_stop(self) -> None:
        with self._lock:
            self._override = "stop"
        self.player.stop()
        self.wake()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                with self._lock:
                    self._tick()
            except Exception:
                logger.exception("Scheduler tick failed")
            self._wake.wait(timeout=self.tick_seconds)
            self._wake.clear()

    def _update_boundary_override(self, in_window: bool) -> None:
        if self._was_in_window is None:
            self._was_in_window = in_window
            return
        if in_window != self._was_in_window:
            if self._override is not None:
                logger.info("Schedule boundary crossed; clearing manual override")
            self._override = None
        self._was_in_window = in_window

    def _resolve_audio_device(self, cfg) -> str | None:
        try:
            self.bt_monitor.connect_now()
        except Exception as exc:
            logger.warning("Bluetooth connect before playback: %s", exc)

        try:
            device = self.bt_monitor.adapter.ensure_audio_route(
                cfg.bluetooth.device_address,
                cfg.bluetooth.device_name,
            )
            self._audio_error = None
            return device
        except Exception as exc:
            self._audio_error = str(exc)
            logger.error("Audio route failed: %s", exc)
            raise

    def _begin_playback(self) -> None:
        cfg = self.config.snapshot()
        playlist = self.config.playlist_path()
        tracks = parse_m3u(playlist)
        if not tracks:
            logger.warning("Playlist is empty: %s", playlist)
            self._audio_error = f"Playlist is empty: {playlist}"
            return

        missing = [str(t) for t in tracks if not t.exists()]
        if missing:
            logger.warning("Missing tracks (mpv may skip): %s", ", ".join(missing[:5]))

        device = self._resolve_audio_device(cfg)
        self.player.start(playlist, volume=cfg.audio.volume, audio_device=device)

    def _tick(self) -> None:
        cfg = self.config.snapshot()
        now = datetime.now()
        in_window = in_schedule_window(now, cfg.schedule.start, cfg.schedule.stop)
        self._update_boundary_override(in_window)

        override = self._override
        should_play = (
            override == "play"
            if override is not None
            else in_window
        )
        playing = self.player.is_playing

        if should_play and not playing:
            logger.info(
                "Starting playback (override=%s, in_window=%s)",
                override,
                in_window,
            )
            try:
                self._begin_playback()
            except Exception:
                # _audio_error set in _resolve_audio_device
                pass

        elif not should_play and playing:
            logger.info(
                "Stopping playback (override=%s, in_window=%s)",
                override,
                in_window,
            )
            self.player.stop()
