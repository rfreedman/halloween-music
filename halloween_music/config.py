"""Thread-safe config loaded from / persisted to YAML."""

from __future__ import annotations

import re
import threading
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def normalize_time(value: str) -> str:
    match = TIME_RE.match(value.strip())
    if not match:
        raise ValueError(f"Invalid time '{value}', expected HH:MM")
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def normalize_mac(value: str) -> str:
    cleaned = value.strip().upper().replace("-", ":")
    if not MAC_RE.match(cleaned):
        raise ValueError(f"Invalid Bluetooth address '{value}'")
    return cleaned


@dataclass
class ScheduleConfig:
    start: str = "17:00"
    stop: str = "22:00"


@dataclass
class BluetoothConfig:
    device_address: str = "AA:BB:CC:DD:EE:FF"
    device_name: str = "Speaker"
    poll_seconds: int = 15
    reconnect_backoff_seconds: int = 30


@dataclass
class AudioConfig:
    volume: int = 70


@dataclass
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 8080


@dataclass
class AppConfig:
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    playlist: str = "playlist.m3u"
    bluetooth: BluetoothConfig = field(default_factory=BluetoothConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    web: WebConfig = field(default_factory=WebConfig)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schedule": {"start": self.schedule.start, "stop": self.schedule.stop},
            "playlist": self.playlist,
            "bluetooth": {
                "device_address": self.bluetooth.device_address,
                "device_name": self.bluetooth.device_name,
                "poll_seconds": self.bluetooth.poll_seconds,
                "reconnect_backoff_seconds": self.bluetooth.reconnect_backoff_seconds,
            },
            "audio": {"volume": self.audio.volume},
            "web": {"host": self.web.host, "port": self.web.port},
        }


class ConfigStore:
    """In-memory config with YAML persistence."""

    def __init__(self, path: Path):
        self.path = path.resolve()
        self._lock = threading.RLock()
        self._config = AppConfig()
        self.load()

    @property
    def root(self) -> Path:
        return self.path.parent

    def load(self) -> AppConfig:
        with self._lock:
            if not self.path.exists():
                self.save()
                return deepcopy(self._config)

            with self.path.open(encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}

            schedule = raw.get("schedule") or {}
            bluetooth = raw.get("bluetooth") or {}
            audio = raw.get("audio") or {}
            web = raw.get("web") or {}

            self._config = AppConfig(
                schedule=ScheduleConfig(
                    start=normalize_time(str(schedule.get("start", "17:00"))),
                    stop=normalize_time(str(schedule.get("stop", "22:00"))),
                ),
                playlist=str(raw.get("playlist", "playlist.m3u")),
                bluetooth=BluetoothConfig(
                    device_address=normalize_mac(
                        str(bluetooth.get("device_address", "AA:BB:CC:DD:EE:FF"))
                    ),
                    device_name=str(bluetooth.get("device_name", "Speaker")),
                    poll_seconds=int(bluetooth.get("poll_seconds", 15)),
                    reconnect_backoff_seconds=int(
                        bluetooth.get("reconnect_backoff_seconds", 30)
                    ),
                ),
                audio=AudioConfig(
                    volume=max(0, min(100, int(audio.get("volume", 70))))
                ),
                web=WebConfig(
                    host=str(web.get("host", "0.0.0.0")),
                    port=int(web.get("port", 8080)),
                ),
            )
            return deepcopy(self._config)

    def snapshot(self) -> AppConfig:
        with self._lock:
            return deepcopy(self._config)

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                yaml.safe_dump(
                    self._config.to_dict(),
                    fh,
                    default_flow_style=False,
                    sort_keys=False,
                )
            tmp.replace(self.path)

    def update_schedule(self, start: str, stop: str) -> AppConfig:
        with self._lock:
            self._config.schedule.start = normalize_time(start)
            self._config.schedule.stop = normalize_time(stop)
            self.save()
            return deepcopy(self._config)

    def update_bluetooth(
        self, device_address: str, device_name: str | None = None
    ) -> AppConfig:
        with self._lock:
            self._config.bluetooth.device_address = normalize_mac(device_address)
            if device_name is not None:
                self._config.bluetooth.device_name = device_name.strip() or self._config.bluetooth.device_name
            self.save()
            return deepcopy(self._config)

    def update_volume(self, volume: int) -> AppConfig:
        with self._lock:
            self._config.audio.volume = max(0, min(100, int(volume)))
            self.save()
            return deepcopy(self._config)

    def playlist_path(self) -> Path:
        path = Path(self.snapshot().playlist)
        if not path.is_absolute():
            path = self.root / path
        return path.resolve()
