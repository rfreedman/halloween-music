"""Bluetooth adapters for macOS and Linux."""

from __future__ import annotations

import sys

from halloween_music.bluetooth.base import BluetoothAdapter
from halloween_music.bluetooth.linux import LinuxBluetooth
from halloween_music.bluetooth.macos import MacOSBluetooth


def create_adapter() -> BluetoothAdapter:
    if sys.platform == "darwin":
        return MacOSBluetooth()
    if sys.platform.startswith("linux"):
        return LinuxBluetooth()
    raise RuntimeError(f"Unsupported platform for Bluetooth: {sys.platform}")


__all__ = ["BluetoothAdapter", "create_adapter", "MacOSBluetooth", "LinuxBluetooth"]
