"""Generate the placeholder Pixel Font Editor application icons."""

from pathlib import Path
import struct
import zlib


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets"
BACKGROUND = (24, 60, 56, 255)
MINT = (217, 233, 168, 255)
CORAL = (223, 112, 77, 255)
PIXEL_ART = (
    "..####..",
    ".##..##.",
    ".##..##.",
    ".######.",
    ".#####..",
    ".##.....",
    ".##..+..",
    ".##.....",
    ".##.....",
    ".##.....",
)


def _set_pixel(pixels: bytearray, size: int, x: int, y: int, color: tuple[int, ...]) -> None:
    offset = (y * size + x) * 4
    pixels[offset : offset + 4] = bytes(color)


def _render_icon(size: int) -> bytes:
    pixels = bytearray(size * size * 4)
    margin = max(1, size // 12)
    radius = max(1, size // 6)
    left, right = margin, size - margin - 1
    top, bottom = margin, size - margin - 1
    inner_left, inner_right = left + radius, right - radius
    inner_top, inner_bottom = top + radius, bottom - radius

    for pixel_y in range(top, bottom + 1):
        nearest_y = min(max(pixel_y, inner_top), inner_bottom)
        for pixel_x in range(left, right + 1):
            nearest_x = min(max(pixel_x, inner_left), inner_right)
            delta_x = pixel_x - nearest_x
            delta_y = pixel_y - nearest_y
            if delta_x * delta_x + delta_y * delta_y <= radius * radius:
                _set_pixel(pixels, size, pixel_x, pixel_y, BACKGROUND)

    pitch = max(1, size // 12)
    pixel_size = max(1, round(pitch * 0.82))
    shape_width = len(PIXEL_ART[0]) * pitch
    shape_height = len(PIXEL_ART) * pitch
    origin_x = (size - shape_width) // 2
    origin_y = (size - shape_height) // 2
    pixel_offset = (pitch - pixel_size) // 2

    for row_index, art_row in enumerate(PIXEL_ART):
        for column_index, art_pixel in enumerate(art_row):
            if art_pixel not in "#+":
                continue
            color = CORAL if art_pixel == "+" else MINT
            pixel_left = origin_x + column_index * pitch + pixel_offset
            pixel_top = origin_y + row_index * pitch + pixel_offset
            for pixel_y in range(pixel_top, pixel_top + pixel_size):
                for pixel_x in range(pixel_left, pixel_left + pixel_size):
                    _set_pixel(pixels, size, pixel_x, pixel_y, color)

    scanlines = b"".join(
        b"\x00" + pixels[row_index * size * 4 : (row_index + 1) * size * 4]
        for row_index in range(size)
    )
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", header) + _png_chunk(
        b"IDAT", zlib.compress(scanlines, 9)
    ) + _png_chunk(b"IEND", b"")


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


def _write_ico(path: Path, sizes: tuple[int, ...]) -> None:
    images = [_render_icon(size) for size in sizes]
    header_size = 6 + 16 * len(images)
    offset = header_size
    entries = []
    for size, image in zip(sizes, images):
        dimension = 0 if size == 256 else size
        entries.append(
            struct.pack(
                "<BBBBHHII",
                dimension,
                dimension,
                0,
                0,
                1,
                32,
                len(image),
                offset,
            )
        )
        offset += len(image)
    path.write_bytes(struct.pack("<HHH", 0, 1, len(images)) + b"".join(entries) + b"".join(images))


def _write_icns(path: Path, sizes: tuple[tuple[bytes, int], ...]) -> None:
    chunks = []
    for chunk_type, size in sizes:
        image = _render_icon(size)
        chunks.append(chunk_type + struct.pack(">I", len(image) + 8) + image)
    body = b"".join(chunks)
    path.write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    (ASSET_DIR / "pixel_font_editor.png").write_bytes(_render_icon(256))
    _write_ico(
        ASSET_DIR / "pixel_font_editor.ico",
        (16, 32, 48, 64, 128, 256),
    )
    _write_icns(
        ASSET_DIR / "pixel_font_editor.icns",
        ((b"icp4", 16), (b"icp5", 32), (b"icp6", 64), (b"ic07", 128),
         (b"ic08", 256), (b"ic09", 512), (b"ic10", 1024)),
    )


if __name__ == "__main__":
    main()