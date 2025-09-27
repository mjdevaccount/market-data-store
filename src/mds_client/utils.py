from __future__ import annotations

import gzip
import io
import json
import sys
from pathlib import Path
from typing import Iterator, Literal, Union, Any, Dict, Type

from .models import Bar, Fundamentals, News, OptionSnap

Kind = Literal["bars", "fundamentals", "news", "options"]

_MODEL_BY_KIND: dict[Kind, Type] = {
    "bars": Bar,
    "fundamentals": Fundamentals,
    "news": News,
    "options": OptionSnap,
}


def _open_stream(path: Union[str, Path]) -> io.BufferedReader:
    if str(path) == "-":
        return sys.stdin.buffer  # type: ignore[return-value]
    p = Path(path)
    raw = p.open("rb")
    # .gz extension or gzip magic
    head = raw.peek(2)[:2] if hasattr(raw, "peek") else raw.read(2)
    if not hasattr(raw, "peek"):
        raw.seek(0)
    if p.suffix == ".gz" or head == b"\x1f\x8b":
        return io.BufferedReader(gzip.GzipFile(fileobj=raw))
    return raw


def iter_ndjson(path: Union[str, Path]) -> Iterator[Dict[str, Any]]:
    """Yields JSON objects per line, skipping blanks/comments."""
    with None if path == "-" else _open_stream(path) as fh:  # type: ignore[assignment]
        stream = sys.stdin.buffer if path == "-" else fh  # type: ignore[assignment]
        for line in stream:  # type: ignore[arg-type]
            if not line or line.strip() in (b"", b"\n"):
                continue
            if line.lstrip().startswith(b"#"):
                continue
            obj = json.loads(line.decode("utf-8"))
            yield obj


def coerce_model(kind: Kind, obj: Dict[str, Any]):
    model_cls = _MODEL_BY_KIND[kind]
    return model_cls(**obj)
