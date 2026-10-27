"""Import bitmap glyphs from U8g2 C font arrays."""

import re

from pixel_font_editor.model import Glyph, MAX_DIMENSION


FONT_ARRAY = re.compile(
    r"\b(?:const\s+)?(?:uint8_t|unsigned\s+char)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*\[\s*(?:\d+)?\s*\][^=]*=\s*"
    r"((?:\"(?:\\.|[^\"\\])*\"\s*)+);",
    re.DOTALL,
)
STRING_LITERAL = re.compile(r'"(?:\\.|[^"\\])*"')


class _BitReader:
    def __init__(self, data: bytes, offset: int) -> None:
        self.data = data
        self.bit_position = offset * 8

    def read(self, bit_count: int) -> int:
        if bit_count == 0:
            return 0
        if not 0 <= bit_count <= 8:
            raise ValueError("unsupported U8g2 bit field width")
        value = 0
        for bit_index in range(bit_count):
            byte_index, byte_bit = divmod(self.bit_position, 8)
            if byte_index >= len(self.data):
                raise ValueError("unexpected end of U8g2 font data")
            value |= ((self.data[byte_index] >> byte_bit) & 1) << bit_index
            self.bit_position += 1
        return value

    def read_signed(self, bit_count: int) -> int:
        if bit_count == 0:
            return 0
        return self.read(bit_count) - (1 << (bit_count - 1))


def _decode_c_string(token: str) -> bytes:
    content = token[1:-1]
    result = bytearray()
    index = 0
    simple_escapes = {
        "\\": 0x5C,
        '"': 0x22,
        "'": 0x27,
        "?": 0x3F,
        "a": 0x07,
        "b": 0x08,
        "f": 0x0C,
        "n": 0x0A,
        "r": 0x0D,
        "t": 0x09,
        "v": 0x0B,
    }
    while index < len(content):
        character = content[index]
        index += 1
        if character != "\\":
            codepoint = ord(character)
            if codepoint > 0x7F:
                result.extend(character.encode("utf-8"))
            else:
                result.append(codepoint)
            continue
        if index == len(content):
            raise ValueError("incomplete escape in U8g2 C string")
        escape = content[index]
        index += 1
        if escape in "01234567":
            digits = escape
            while index < len(content) and len(digits) < 3 and content[index] in "01234567":
                digits += content[index]
                index += 1
            result.append(int(digits, 8) & 0xFF)
        elif escape == "x":
            start = index
            while index < len(content) and content[index] in "0123456789abcdefABCDEF":
                index += 1
            if index == start:
                raise ValueError("invalid hexadecimal escape in U8g2 C string")
            result.append(int(content[start:index], 16) & 0xFF)
        elif escape in simple_escapes:
            result.append(simple_escapes[escape])
        else:
            raise ValueError(f"unsupported escape sequence \\{escape} in U8g2 C string")
    return bytes(result)


def _extract_font_array(source: str) -> tuple[str, bytes]:
    declaration = FONT_ARRAY.search(source)
    if declaration is None:
        raise ValueError("no U8g2 font string array was found")
    literals = STRING_LITERAL.findall(declaration.group(2))
    data = b"".join(_decode_c_string(literal) for literal in literals)
    if len(data) < 23:
        raise ValueError("U8g2 font header is incomplete")
    return declaration.group(1), data


def extract_u8g2_c_header(source: str) -> str:
    """Return all source text before the U8g2 font array declaration."""
    declaration = FONT_ARRAY.search(source)
    if declaration is None:
        raise ValueError("no U8g2 font string array was found")
    return source[: declaration.start()]


def _decode_glyph(
    data: bytes,
    glyph_offset: int,
    codepoint: int,
    header: bytes,
) -> Glyph:
    bits = _BitReader(data, glyph_offset)
    width = bits.read(header[4])
    height = bits.read(header[5])
    x_offset = bits.read_signed(header[6])
    y_offset = bits.read_signed(header[7])
    advance = bits.read_signed(header[8])

    if width > MAX_DIMENSION or height > MAX_DIMENSION:
        raise ValueError(
            f"U+{codepoint:04X} is {width}x{height}; dimensions are limited to "
            f"{MAX_DIMENSION}x{MAX_DIMENSION}"
        )

    pixels = width * height
    bitmap = [0] * pixels
    position = 0
    while position < pixels:
        zero_run = bits.read(header[2])
        one_run = bits.read(header[3])
        while True:
            position += zero_run
            for _ in range(one_run):
                if position < pixels:
                    bitmap[position] = 1
                position += 1
            if bits.read(1) == 0 or position >= pixels:
                break

    rows = []
    for row_index in range(height):
        row = 0
        for column in range(width):
            if bitmap[row_index * width + column]:
                row |= 1 << (width - 1 - column)
        rows.append(row)

    description = (
        f"U+{codepoint:04X} {width}x{height} "
        f"x{x_offset} y{y_offset} advance{advance}"
    )
    return Glyph(max(width, 1), max(height, 1), rows if width and height else None, description)


def _decode_byte_glyphs(data: bytes, header: bytes) -> list[Glyph]:
    glyphs = []
    offset = 23
    while offset + 2 <= len(data):
        codepoint, length = data[offset], data[offset + 1]
        if length == 0:
            break
        if length < 2 or offset + length > len(data):
            raise ValueError("invalid U8g2 glyph length")
        glyphs.append(_decode_glyph(data, offset + 2, codepoint, header))
        offset += length
    return glyphs


def _decode_unicode_glyphs(data: bytes, header: bytes) -> list[Glyph]:
    table_offset = int.from_bytes(header[21:23], "big")
    if table_offset == 0:
        return []
    table_start = 23 + table_offset
    table_entries = []
    cursor = table_start
    while cursor + 4 <= len(data):
        block_offset = int.from_bytes(data[cursor : cursor + 2], "big")
        last_codepoint = int.from_bytes(data[cursor + 2 : cursor + 4], "big")
        table_entries.append((block_offset, last_codepoint))
        cursor += 4
        if last_codepoint == 0xFFFF:
            break
    if not table_entries or table_entries[-1][1] != 0xFFFF:
        raise ValueError("invalid U8g2 Unicode lookup table")

    glyphs = []
    cursor = table_start + table_entries[0][0]
    while cursor + 3 <= len(data):
        codepoint = int.from_bytes(data[cursor : cursor + 2], "big")
        length = data[cursor + 2]
        if codepoint == 0 or length == 0:
            break
        if length < 3 or cursor + length > len(data):
            raise ValueError("invalid U8g2 Unicode glyph length")
        glyphs.append(_decode_glyph(data, cursor + 3, codepoint, header))
        cursor += length
    return glyphs


def parse_u8g2_font_with_metadata(
    source: str,
) -> tuple[str, list[Glyph], bytes]:
    """Parse a U8g2 font and return its complete 23-byte header."""
    name, data = _extract_font_array(source)
    header = data[:23]
    glyphs = _decode_byte_glyphs(data, header)
    glyphs.extend(_decode_unicode_glyphs(data, header))
    if not glyphs:
        raise ValueError("U8g2 font contains no glyphs")
    width = max(glyph.width for glyph in glyphs)
    height = max(glyph.height for glyph in glyphs)
    for glyph in glyphs:
        glyph.resize(width, height)
    return name, glyphs, header


def parse_u8g2_font(source: str) -> tuple[str, list[Glyph]]:
    """Parse a U8g2 C font array into editable glyphs."""
    name, glyphs, _header = parse_u8g2_font_with_metadata(source)
    return name, glyphs