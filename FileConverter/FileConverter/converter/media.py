"""Audio and video via ffmpeg (only enabled when ffmpeg is available)."""
from __future__ import annotations

from pathlib import Path

from .engine import register
from .util import ffmpeg_path, run

VIDEO = ["mp4", "mkv", "avi", "mov", "webm"]
AUDIO = ["mp3", "wav", "flac", "ogg", "m4a", "aac"]

EXTRA_ARGS = {
    "mp3": ["-vn", "-codec:a", "libmp3lame", "-q:a", "2"],
    "wav": ["-vn"], "flac": ["-vn"], "ogg": ["-vn", "-codec:a", "libvorbis", "-q:a", "5"],
    "m4a": ["-vn", "-codec:a", "aac", "-b:a", "192k"], "aac": ["-vn", "-codec:a", "aac", "-b:a", "192k"],
    "mp4": ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-codec:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-codec:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-pix_fmt", "yuv420p"],
    "webm": ["-codec:v", "libvpx-vp9", "-b:v", "0", "-crf", "33", "-row-mt", "1",
             "-deadline", "realtime", "-codec:a", "libopus"],
    "gif": ["-an", "-vf", "fps=12,scale='min(640,iw)':-1:flags=lanczos,split[a][b];"
                         "[a]palettegen[p];[b][p]paletteuse"],
}


def ffmpeg_convert(src: Path, dst: Path) -> list[Path]:
    fmt = dst.suffix[1:].lower()
    run([ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
         *EXTRA_ARGS.get(fmt, []), str(dst)], timeout=3600)
    return [dst]


_ok = lambda: ffmpeg_path() is not None  # noqa: E731
register(VIDEO, VIDEO + AUDIO + ["gif"], ffmpeg_convert, name="ffmpeg", cost=10, available=_ok, terminal=True)
register(AUDIO, AUDIO, ffmpeg_convert, name="ffmpeg", cost=10, available=_ok, terminal=True)
# animated GIF -> video
register(["gif"], ["mp4", "webm"], ffmpeg_convert, name="ffmpeg", cost=10, available=_ok, terminal=True)
