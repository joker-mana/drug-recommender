from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def iter_json_array(
    path: Path,
    array_key: str = "results",
    chunk_size: int = 8 * 1024 * 1024,
) -> Iterator[dict[str, Any]]:
    """Stream objects from a large top-level JSON array without loading it all."""
    decoder = json.JSONDecoder()
    marker = f'"{array_key}"'
    buffer = ""
    position = 0
    started = False
    eof = False

    with path.open("r", encoding="utf-8") as handle:
        while True:
            if not started:
                if len(buffer) - position < chunk_size and not eof:
                    piece = handle.read(chunk_size)
                    eof = not piece
                    buffer = buffer[position:] + piece
                    position = 0
                marker_pos = buffer.find(marker, position)
                if marker_pos < 0:
                    if eof:
                        raise ValueError(f"Could not find {marker!r} in {path}")
                    continue
                array_pos = buffer.find("[", marker_pos + len(marker))
                if array_pos < 0:
                    if eof:
                        raise ValueError(f"Could not find array after {marker!r}")
                    continue
                position = array_pos + 1
                started = True

            while position < len(buffer) and buffer[position] in " \t\r\n,":
                position += 1
            if position >= len(buffer):
                if eof:
                    return
                piece = handle.read(chunk_size)
                eof = not piece
                buffer = buffer[position:] + piece
                position = 0
                continue
            if buffer[position] == "]":
                return
            try:
                item, end = decoder.raw_decode(buffer, position)
            except json.JSONDecodeError:
                if eof:
                    raise
                piece = handle.read(chunk_size)
                eof = not piece
                buffer = buffer[position:] + piece
                position = 0
                continue

            yield item
            position = end
            if position > chunk_size * 2:
                buffer = buffer[position:]
                position = 0
