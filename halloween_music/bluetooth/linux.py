"""Linux Bluetooth via bluetoothctl (Raspberry Pi)."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess

from halloween_music.audio_route import ensure_linux_default_sink
from halloween_music.bluetooth.base import BluetoothAdapter

logger = logging.getLogger(__name__)


class LinuxBluetooth(BluetoothAdapter):
    def __init__(self) -> None:
        self._bin = shutil.which("bluetoothctl")
        if not self._bin:
            logger.warning("bluetoothctl not found; install bluez")

    def _run(self, *args: str, timeout: float = 30) -> subprocess.CompletedProcess[str]:
        if not self._bin:
            raise RuntimeError("bluetoothctl is not installed (install bluez)")
        return subprocess.run(
            [self._bin, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def is_connected(self, address: str) -> bool:
        result = self._run("info", address, timeout=10)
        text = result.stdout or ""
        match = re.search(r"Connected:\s*(yes|no)", text, re.IGNORECASE)
        return bool(match and match.group(1).lower() == "yes")

    def connect(self, address: str) -> None:
        result = self._run("connect", address, timeout=45)
        combined = f"{result.stdout}\n{result.stderr}".strip()
        if result.returncode != 0 and "already connected" not in combined.lower():
            raise RuntimeError(combined or "connect failed")
        if not self.is_connected(address):
            raise RuntimeError(f"Bluetooth device {address} did not connect")

    def disconnect(self, address: str) -> None:
        result = self._run("disconnect", address, timeout=20)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "disconnect failed").strip()
            logger.warning("Disconnect %s: %s", address, err)

    def ensure_audio_route(self, address: str, name: str | None = None) -> str | None:
        ensure_linux_default_sink(address)
        return None
