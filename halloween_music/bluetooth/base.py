"""Bluetooth adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class BluetoothStatus:
    connected: bool
    address: str
    name: str
    reconnecting: bool = False
    last_error: str | None = None


class BluetoothAdapter(ABC):
    @abstractmethod
    def is_connected(self, address: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def connect(self, address: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def disconnect(self, address: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def ensure_audio_route(self, address: str, name: str | None = None) -> str | None:
        """Select output for playback. Returns mpv --audio-device id, or None for system default."""
        raise NotImplementedError
