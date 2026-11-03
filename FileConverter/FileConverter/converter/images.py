"""Images with Pillow: png, jpg, bmp, gif, tiff, webp, ico, and image -> pdf."""
from __future__ import annotations

from pathlib import Path

from .engine import register

IMAGE_FORMATS = ["png", "jpg", "bmp", "gif", "tiff", "webp", "ico"]
NO_ALPHA = {"jpg", "bmp", "pdf"}


def _pillow_ok() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def _flatten(img):
    """Put transparent images on a white background (JPG/BMP/PDF have no alpha)."""
    from PIL import Image
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, "white")
        bg.paste(img, mask=img.split()[-1])
        return bg
    return img.convert("RGB")


def convert_image(src: Path, dst: Path) -> list[Path]:
    from PIL import Image, ImageOps
    fmt = dst.suffix[1:].lower()
    with Image.open(src) as im:
        frames_kept = fmt in ("gif", "webp", "tiff") and getattr(im, "n_frames", 1) > 1
        if frames_kept:  # keep animation
            im.save(dst, save_all=True, loop=im.info.get("loop", 0),
                    duration=im.info.get("duration", 100))
            return [dst]
        img = ImageOps.exif_transpose(im)  # respect phone-camera rotation
        img.load()
    if fmt in NO_ALPHA:
        img = _flatten(img)
    elif img.mode not in ("RGB", "RGBA", "L", "LA", "P"):
        img = img.convert("RGBA")
    if fmt == "jpg":
        img.save(dst, "JPEG", quality=92, optimize=True)
    elif fmt == "ico":
        img = img.convert("RGBA")
        sizes = [s for s in [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
                 if s[0] <= max(img.size)] or [(16, 16)]
        img.save(dst, "ICO", sizes=sizes)
    elif fmt == "webp":
        img.save(dst, "WEBP", quality=90)
    elif fmt == "pdf":
        img.save(dst, "PDF", resolution=150)
    else:
        img.save(dst)
    return [dst]


register(IMAGE_FORMATS, IMAGE_FORMATS + ["pdf"], convert_image, name="Pillow",
         cost=10, available=_pillow_ok, terminal=True)
