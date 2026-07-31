"""Convert existing uploaded source photos to the same 300KB limit as new uploads.

Usage: python compress_uploads_to_300kb.py /data/hangong/uploads
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image, ImageOps


MAX_BYTES = 300 * 1024
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
SKIP_DIRECTORIES = {"cards", "temp_ids"}


def _scaled(image: Image.Image, scale: float) -> Image.Image:
    width = max(1, round(image.width * scale))
    height = max(1, round(image.height * scale))
    if (width, height) == image.size:
        return image.copy()
    return image.resize((width, height), Image.Resampling.LANCZOS)


def _encode_jpeg(image: Image.Image) -> bytes:
    rgb = image.convert("RGB")
    best = b""
    scale = min(1.0, 1600 / max(rgb.size))
    for _ in range(5):
        candidate = _scaled(rgb, scale)
        low, high = 5, 95
        for _ in range(9):
            quality = (low + high) // 2
            buffer = io.BytesIO()
            candidate.save(buffer, "JPEG", quality=quality, optimize=True)
            content = buffer.getvalue()
            if len(content) <= MAX_BYTES:
                best = content
                low = quality + 1
            else:
                high = quality - 1
        if best:
            return best
        scale *= 0.75
    return best


def _encode_png(image: Image.Image) -> bytes:
    rgb = image.convert("RGB")
    scale = min(1.0, 1600 / max(rgb.size))
    best = b""
    for _ in range(5):
        candidate = _scaled(rgb, scale)
        for colors in (256, 128, 64, 32, 16):
            palette = candidate.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
            buffer = io.BytesIO()
            palette.save(buffer, "PNG", optimize=True, compress_level=9)
            content = buffer.getvalue()
            if len(content) <= MAX_BYTES:
                return content
            if not best or len(content) < len(best):
                best = content
        scale *= 0.75
    return best


def compress_photo(path: Path) -> bool:
    if path.stat().st_size <= MAX_BYTES:
        return False
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source)
        encoded = _encode_png(image) if path.suffix.lower() == ".png" else _encode_jpeg(image)
    if not encoded or len(encoded) > MAX_BYTES:
        raise RuntimeError(f"无法压缩到 300KB：{path}")
    temporary = path.with_suffix(path.suffix + ".compressing")
    temporary.write_bytes(encoded)
    temporary.replace(path)
    return True


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python compress_uploads_to_300kb.py /path/to/uploads")
        return 2
    root = Path(sys.argv[1])
    if not root.is_dir():
        print(f"Uploads directory not found: {root}")
        return 2
    converted = skipped = failures = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if any(part in SKIP_DIRECTORIES for part in path.relative_to(root).parts):
            continue
        try:
            if compress_photo(path):
                converted += 1
            else:
                skipped += 1
        except Exception as error:
            failures += 1
            print(f"FAILED {path}: {error}")
    print(f"converted={converted} already_within_limit={skipped} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
