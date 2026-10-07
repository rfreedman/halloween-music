#!/usr/bin/env python3
"""Halloween music player — scheduled Bluetooth playback with web UI."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path

from halloween_music.bluetooth import create_adapter
from halloween_music.bluetooth.monitor import BluetoothMonitor
from halloween_music.config import ConfigStore
from halloween_music.player import Player
from halloween_music.scheduler import Scheduler
from halloween_music.web.app import create_app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Halloween music scheduler")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config.yaml (default: ./config.yaml)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logger = logging.getLogger("halloween_music")

    config_path = Path(args.config).expanduser().resolve()
    config = ConfigStore(config_path)
    cfg = config.snapshot()

    player = Player()
    try:
        adapter = create_adapter()
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 1

    bt_monitor = BluetoothMonitor(config, adapter, player)
    scheduler = Scheduler(config, player, bt_monitor)
    app = create_app(config, player, scheduler, bt_monitor)

    bt_monitor.start()
    scheduler.start()

    def shutdown(*_args) -> None:
        logger.info("Shutting down…")
        scheduler.stop()
        bt_monitor.stop()
        player.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info(
        "Schedule %s–%s | playlist %s | web http://%s:%s",
        cfg.schedule.start,
        cfg.schedule.stop,
        config.playlist_path(),
        cfg.web.host,
        cfg.web.port,
    )
    # evaluate immediately so we don't wait for first tick
    scheduler.evaluate_now()

    app.run(host=cfg.web.host, port=cfg.web.port, threaded=True, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
