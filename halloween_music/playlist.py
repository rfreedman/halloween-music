"""Parse .m3u playlists."""

from __future__ import annotations

from pathlib import Path


def parse_m3u(playlist_path: Path) -> list[Path]:
    """Return absolute audio paths from an .m3u file."""
    playlist_path = playlist_path.resolve()
    if not playlist_path.exists():
        raise FileNotFoundError(f"Playlist not found: {playlist_path}")

    base = playlist_path.parent
    tracks: list[Path] = []

    with playlist_path.open(encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("file://"):
                line = line[7:]
            path = Path(line)
            if not path.is_absolute():
                path = base / path
            tracks.append(path.resolve())

    return tracks
