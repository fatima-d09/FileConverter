"""
Conversion engine.

Every backend registers small one-step converters (e.g. "pdf -> docx").
The engine finds the cheapest chain of steps between any two formats
(e.g. pdf -> docx -> html -> md) and runs it, using a temp folder for
intermediate files.
"""
from __future__ import annotations

import heapq
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

# Aliases so "photo.jpeg" and "photo.jpg" are treated the same, etc.
ALIASES = {
    "jpeg": "jpg", "htm": "html", "markdown": "md", "tif": "tiff",
    "text": "txt", "xhtml": "html", "yml": "yaml",
}

# Human-friendly labels for the format dropdown.
LABELS = {
    "pdf": "PDF document", "docx": "Word document", "doc": "Word 97-2003",
    "odt": "OpenDocument text", "rtf": "Rich Text", "html": "Web page (HTML)",
    "md": "Markdown", "txt": "Plain text", "epub": "E-book (EPUB)",
    "tex": "LaTeX", "rst": "reStructuredText", "ipynb": "Jupyter notebook",
    "png": "PNG image", "jpg": "JPEG image", "bmp": "Bitmap image",
    "gif": "GIF image", "tiff": "TIFF image", "webp": "WebP image",
    "ico": "Windows icon", "csv": "CSV table", "xlsx": "Excel workbook",
    "xls": "Excel 97-2003", "json": "JSON data", "pptx": "PowerPoint",
    "ppt": "PowerPoint 97-2003", "odp": "OpenDocument slides",
    "ods": "OpenDocument sheet", "mp4": "MP4 video", "mkv": "MKV video",
    "avi": "AVI video", "mov": "QuickTime video", "webm": "WebM video",
    "mp3": "MP3 audio", "wav": "WAV audio", "flac": "FLAC audio",
    "ogg": "OGG audio", "m4a": "M4A audio", "aac": "AAC audio",
}


def norm(fmt: str) -> str:
    fmt = fmt.lower().lstrip(".")
    return ALIASES.get(fmt, fmt)


def format_of(path: str | Path) -> str:
    return norm(Path(path).suffix)


class ConversionError(Exception):
    pass


# A converter function receives (source_file, destination_file) and returns
# the list of files it actually produced (usually [destination_file], but
# e.g. a 10-page PDF -> PNG produces 10 files).
ConvertFunc = Callable[[Path, Path], list]


@dataclass
class Step:
    src: str
    dst: str
    func: ConvertFunc
    name: str                       # e.g. "pandoc", "Pillow"
    cost: int = 10                  # lower = preferred
    terminal: bool = False          # nothing can be chained after this step
    available: Callable[[], bool] = field(default=lambda: True)


_STEPS: list[Step] = []


def register(srcs: Iterable[str], dsts: Iterable[str], func: ConvertFunc, *,
             name: str, cost: int = 10, terminal: bool = False,
             available: Callable[[], bool] = lambda: True,
             allow_same: bool = False) -> None:
    for s in srcs:
        for d in dsts:
            s2, d2 = norm(s), norm(d)
            if s2 == d2 and not allow_same:
                continue
            _STEPS.append(Step(s2, d2, func, name, cost, terminal, available))


_avail_cache: dict[int, bool] = {}


def _usable(step: Step) -> bool:
    key = id(step.available)
    if key not in _avail_cache:
        try:
            _avail_cache[key] = bool(step.available())
        except Exception:
            _avail_cache[key] = False
    return _avail_cache[key]


def _graph() -> dict[str, list[Step]]:
    g: dict[str, list[Step]] = {}
    for st in _STEPS:
        if _usable(st):
            g.setdefault(st.src, []).append(st)
    return g


def find_route(src: str, dst: str) -> list[Step] | None:
    """Cheapest chain of steps from src to dst (Dijkstra)."""
    src, dst = norm(src), norm(dst)
    if src == dst:
        return None
    g = _graph()
    heap: list = [(0, 0, src, [])]
    best: dict[str, int] = {src: 0}
    counter = 0
    while heap:
        cost, _, fmt, path = heapq.heappop(heap)
        if fmt == dst:
            return path
        if path and path[-1].terminal:
            continue
        for st in g.get(fmt, []):
            nc = cost + st.cost
            if nc < best.get(st.dst, 1 << 30) and len(path) < 5:
                best[st.dst] = nc
                counter += 1
                heapq.heappush(heap, (nc, counter, st.dst, path + [st]))
    return None


def targets_for(src: str) -> list[str]:
    """Every format reachable from `src`, sorted."""
    src = norm(src)
    return sorted(f for f in all_formats() if f != src and find_route(src, f))


def all_formats() -> set[str]:
    g = _graph()
    fmts = set(g)
    for steps in g.values():
        fmts.update(s.dst for s in steps)
    return fmts


def input_formats() -> list[str]:
    return sorted(_graph())


def describe_route(route: list[Step]) -> str:
    if not route:
        return ""
    return " → ".join([route[0].src] + [s.dst for s in route])


def unique_path(path: Path) -> Path:
    """'report.docx' -> 'report (1).docx' if it already exists."""
    if not path.exists():
        return path
    i = 1
    while True:
        p = path.with_name(f"{path.stem} ({i}){path.suffix}")
        if not p.exists():
            return p
        i += 1


def convert(src_file: str | Path, dst_fmt: str, out_dir: str | Path | None = None,
            log: Callable[[str], None] = lambda m: None) -> list[Path]:
    """Convert one file. Returns the list of output files."""
    src_file = Path(src_file).resolve()
    if not src_file.is_file():
        raise ConversionError(f"File not found: {src_file}")
    src_fmt = format_of(src_file)
    dst_fmt = norm(dst_fmt)
    route = find_route(src_fmt, dst_fmt)
    if not route:
        raise ConversionError(f"No way to convert .{src_fmt} to .{dst_fmt} "
                              "with the tools installed.")
    out_dir = Path(out_dir).resolve() if out_dir else src_file.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    final = unique_path(out_dir / f"{src_file.stem}.{dst_fmt}")

    log(f"{src_file.name}: {describe_route(route)}")
    with tempfile.TemporaryDirectory(prefix="fileconv_") as tmp:
        current = src_file
        outputs: list[Path] = []
        for i, step in enumerate(route):
            last = i == len(route) - 1
            target = final if last else Path(tmp) / f"step{i}_{src_file.stem}.{step.dst}"
            log(f"   {step.src} → {step.dst}  ({step.name})")
            try:
                produced = step.func(current, target)
            except ConversionError:
                raise
            except Exception as e:  # turn library errors into readable ones
                raise ConversionError(f"{step.name} failed on {step.src}→{step.dst}: {e}") from e
            outputs = [Path(p) for p in (produced or [target])]
            if not outputs or not all(p.exists() for p in outputs):
                raise ConversionError(f"{step.name} did not produce an output file.")
            current = outputs[0]
        return outputs


def which(*names: str) -> str | None:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None
