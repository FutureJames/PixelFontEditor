"""Export editable glyphs as U8g2 C font arrays."""

import re

from pixel_font_editor.model import Glyph


U8G2_DESCRIPTION = re.compile(
    r"^U\+([0-9A-Fa-f]{4,6})\s+(\d+)x(\d+)\s+"
    r"x(-?\d+)\s+y(-?\d+)\s+advance(-?\d+)$"
)
U8G2_DATA = re.compile(
    r"^(\d+)x(\d+)\s+x(-?\d+)\s+y(-?\d+)\s+advance(-?\d+)$"
)


class _BitWriter:
    def __init__(self) -> None:
        self.data = bytearray()
        self.bit_position = 0

    def write(self, value: int, bit_count: int) -> None:
        if bit_count == 0:
            if value != 0:
                raise ValueError("value does not fit its U8g2 bit field")
            return
        if value < 0 or value >= 1 << bit_count:
            raise ValueError("value does not fit its U8g2 bit field")
        for bit_index in range(bit_count):
            byte_index, byte_bit = divmod(self.bit_position, 8)
            if byte_index == len(self.data):
                self.data.append(0)
            if value & (1 << bit_index):
                self.data[byte_index] |= 1 << byte_bit
            self.bit_position += 1

    def write_signed(self, value: int, bit_count: int) -> None:
        if bit_count == 0:
            if value != 0:
                raise ValueError("value does not fit its U8g2 signed bit field")
            return
        self.write(value + (1 << (bit_count - 1)), bit_count)


def _bit_width(value: int) -> int:
    return value.bit_length()


def _signed_bit_width(values: list[int]) -> int:
    for bit_count in range(9):
        low = -(1 << (bit_count - 1)) if bit_count else 0
        high = (1 << (bit_count - 1)) - 1 if bit_count else 0
        if all(low <= value <= high for value in values):
            return bit_count
    raise ValueError("U8g2 signed glyph metrics must fit in 8 bits")


def _identifier(name: str) -> str:
    identifier = re.sub(r"\W", "_", name)
    if not identifier or identifier[0].isdigit():
        identifier = f"font_{identifier}"
    return identifier


def _escape_c_string_byte(value: int, next_value: int | None = None) -> str:
    if 0x20 <= value <= 0x7E:
        character = chr(value)
        if character in ('"', "\\", "?"):
            return "\\" + character
        return character
    octal = f"{value:o}"
    if next_value is not None and 0x30 <= next_value <= 0x37 and len(octal) < 3:
        octal = octal.zfill(3)
    return f"\\{octal}"


def _source_records(glyphs: list[Glyph]) -> list[tuple[int, int, int, int, int, int, list[int]]]:
    parsed = [
        (
            U8G2_DATA.fullmatch(glyph.u8g2_data),
            U8G2_DESCRIPTION.fullmatch(glyph.description),
        )
        for glyph in glyphs
    ]
    preserve_metadata = bool(glyphs) and all(
        data_match is not None or description_match is not None
        for data_match, description_match in parsed
    )
    records = []

    for index, (glyph, (data_match, description_match)) in enumerate(
        zip(glyphs, parsed)
    ):
        glyph_rows = glyph.rows if glyph.rows is not None else [0] * glyph.height
        if preserve_metadata:
            if data_match is not None:
                codepoint = glyph.codepoint
                if codepoint is None:
                    codepoint = (
                        ord(glyph.description)
                        if len(glyph.description) == 1
                        else index + 32
                    )
                source_width = int(data_match.group(1))
                source_height = int(data_match.group(2))
                x_offset = int(data_match.group(3))
                y_offset = int(data_match.group(4))
                advance = int(data_match.group(5))
            else:
                # Legacy glyphs store the code point and metrics in description.
                codepoint = int(description_match.group(1), 16)  # type: ignore[union-attr]
                source_width = int(description_match.group(2))  # type: ignore[union-attr]
                source_height = int(description_match.group(3))  # type: ignore[union-attr]
                x_offset = int(description_match.group(4))  # type: ignore[union-attr]
                y_offset = int(description_match.group(5))  # type: ignore[union-attr]
                advance = int(description_match.group(6))  # type: ignore[union-attr]
            width = min(source_width, glyph.width)
            height = min(source_height, glyph.height)
            for y in range(glyph.height):
                for x in range(glyph.width):
                    if glyph_rows[y] & (1 << (glyph.width - 1 - x)):
                        width = max(width, x + 1)
                        height = max(height, y + 1)
        else:
            codepoint = glyph.codepoint if glyph.codepoint is not None else index + 32
            width, height = glyph.width, glyph.height
            x_offset, y_offset, advance = 0, 0, width

        if not 0 < codepoint <= 0xFFFF:
            raise ValueError(f"U+{codepoint:04X} is not a supported U8g2 code point")
        if codepoint > 0x10FFFF:
            raise ValueError("U8g2 code points must not exceed U+10FFFF")

        rows = []
        for y in range(height):
            if y >= glyph.height:
                rows.append(0)
            elif width == 0:
                rows.append(0)
            else:
                rows.append(glyph_rows[y] >> (glyph.width - width))
        records.append((codepoint, width, height, x_offset, y_offset, advance, rows))

    codepoints = [record[0] for record in records]
    if codepoints != sorted(set(codepoints)):
        raise ValueError("U8g2 glyph code points must be unique and in ascending order")
    return records


def _run_pairs(
    pixels: list[int],
    max_zero_run: int = 255,
    max_one_run: int = 255,
) -> list[tuple[int, int, int]]:
    pairs = []
    position = 0
    while position < len(pixels):
        zero_run = 0
        while (
            position < len(pixels)
            and pixels[position] == 0
            and zero_run < max_zero_run
        ):
            zero_run += 1
            position += 1
        one_run = 0
        while (
            position < len(pixels)
            and pixels[position] == 1
            and one_run < max_one_run
        ):
            one_run += 1
            position += 1
        if zero_run == 0 and one_run == 0:
            raise ValueError(
                "cached U8g2 RLE widths cannot represent the edited glyph pixels"
            )
        pairs.append((zero_run, one_run, position))
    return pairs


def _encode_record(
    record: tuple[int, int, int, int, int, int, list[int]],
    field_widths: tuple[int, int, int, int, int, int, int],
) -> bytes:
    codepoint, width, height, x_offset, y_offset, advance, rows = record
    bits_width, bits_height, bits_x, bits_y, bits_advance, bits_zero, bits_one = field_widths
    bits = _BitWriter()
    bits.write(width, bits_width)
    bits.write(height, bits_height)
    bits.write_signed(x_offset, bits_x)
    bits.write_signed(y_offset, bits_y)
    bits.write_signed(advance, bits_advance)
    pixels = [
        (rows[y] >> (width - 1 - x)) & 1
        for y in range(height)
        for x in range(width)
    ]
    pairs = _run_pairs(pixels, (1 << bits_zero) - 1, (1 << bits_one) - 1)
    pair_index = 0
    while pair_index < len(pairs):
        zero_run, one_run, _ = pairs[pair_index]
        repeat_count = 1
        while (
            pair_index + repeat_count < len(pairs)
            and pairs[pair_index + repeat_count][:2] == (zero_run, one_run)
        ):
            repeat_count += 1
        bits.write(zero_run, bits_zero)
        bits.write(one_run, bits_one)
        for repeat_index in range(repeat_count):
            bits.write(int(repeat_index + 1 < repeat_count), 1)
        pair_index += repeat_count
    payload = bytes(bits.data[: (bits.bit_position + 7) // 8])
    if codepoint <= 0xFF:
        if len(payload) + 2 > 0xFF:
            raise ValueError(f"U+{codepoint:04X} exceeds the U8g2 glyph record size limit")
        return bytes((codepoint, len(payload) + 2)) + payload
    if len(payload) + 3 > 0xFF:
        raise ValueError(f"U+{codepoint:04X} exceeds the U8g2 glyph record size limit")
    return codepoint.to_bytes(2, "big") + bytes((len(payload) + 3,)) + payload


def render_u8g2_font(
    name: str,
    glyphs: list[Glyph],
    font_header: bytes | None = None,
    rle_widths: tuple[int, int] | None = None,
    source_header: str = "",
) -> str:
    """Render glyphs as a U8g2 C font array."""
    if not glyphs:
        raise ValueError("at least one glyph is required")
    identifier = _identifier(name)
    records = _source_records(glyphs)
    x_offsets = [record[3] for record in records]
    y_offsets = [record[4] for record in records]
    advances = [record[5] for record in records]
    pixel_streams = [
        [
            (record[6][y] >> (record[1] - 1 - x)) & 1
            for y in range(record[2])
            for x in range(record[1])
        ]
        for record in records
    ]
    if font_header is not None:
        if len(font_header) != 23:
            raise ValueError("cached U8g2 font header must be exactly 23 bytes")
        cached_widths = (font_header[2], font_header[3])
        if rle_widths is not None and rle_widths != cached_widths:
            raise ValueError("RLE widths do not match the cached U8g2 header")
        rle_widths = cached_widths

    if rle_widths is None:
        run_pairs = [_run_pairs(pixels) for pixels in pixel_streams]
        max_zero = max((zero for pairs in run_pairs for zero, _, _ in pairs), default=0)
        max_one = max((one for pairs in run_pairs for _, one, _ in pairs), default=0)
        bits_zero, bits_one = _bit_width(max_zero), _bit_width(max_one)
    else:
        bits_zero, bits_one = rle_widths
        if not 0 <= bits_zero <= 8 or not 0 <= bits_one <= 8:
            raise ValueError("U8g2 RLE widths must be between 0 and 8 bits")
        max_zero_run = (1 << bits_zero) - 1
        max_one_run = (1 << bits_one) - 1
        for pixels in pixel_streams:
            _run_pairs(pixels, max_zero_run, max_one_run)
    if font_header is None:
        field_widths = (
            _bit_width(max((record[1] for record in records), default=0)),
            _bit_width(max((record[2] for record in records), default=0)),
            _signed_bit_width(x_offsets),
            _signed_bit_width(y_offsets),
            _signed_bit_width(advances),
            bits_zero,
            bits_one,
        )
    else:
        field_widths = (
            font_header[4],
            font_header[5],
            font_header[6],
            font_header[7],
            font_header[8],
            bits_zero,
            bits_one,
        )

    byte_records = [record for record in records if record[0] <= 0xFF]
    unicode_records = [record for record in records if record[0] > 0xFF]
    byte_data = bytearray()
    upper_a_offset = 0
    lower_a_offset = 0
    for record in byte_records:
        if record[0] == ord("A"):
            upper_a_offset = len(byte_data)
        elif record[0] == ord("a"):
            lower_a_offset = len(byte_data)
        byte_data.extend(_encode_record(record, field_widths))
    byte_data.extend((0, 0))

    unicode_data = bytearray()
    unicode_offset = 0
    if unicode_records:
        unicode_offset = len(byte_data)
        unicode_table = bytes((0, 4, 0xFF, 0xFF))
        unicode_data.extend(unicode_table)
        for record in unicode_records:
            unicode_data.extend(_encode_record(record, field_widths))
        unicode_data.extend((0, 0, 0))

    if max((upper_a_offset, lower_a_offset, unicode_offset), default=0) > 0xFFFF:
        raise ValueError("U8g2 font lookup offsets exceed the 16-bit format limit")

    max_width = max((record[1] for record in records), default=0)
    max_height = max((record[2] for record in records), default=0)
    x_offset = min(x_offsets, default=0)
    y_offset = max(y_offsets, default=0)
    if font_header is None:
        header = bytearray(
            (
                min(len(records), 0xFF),
                0,
                bits_zero,
                bits_one,
                field_widths[0],
                field_widths[1],
                field_widths[2],
                field_widths[3],
                field_widths[4],
                max_width,
                max_height,
                x_offset & 0xFF,
                y_offset & 0xFF,
                max_height,
                y_offset & 0xFF,
                max_height,
                y_offset & 0xFF,
            )
        )
    else:
        header = bytearray(font_header)
        header[0] = min(len(records), 0xFF)
    if font_header is None:
        header.extend(upper_a_offset.to_bytes(2, "big"))
        header.extend(lower_a_offset.to_bytes(2, "big"))
        header.extend(unicode_offset.to_bytes(2, "big"))
    else:
        header[17:19] = upper_a_offset.to_bytes(2, "big")
        header[19:21] = lower_a_offset.to_bytes(2, "big")
        header[21:23] = unicode_offset.to_bytes(2, "big")
    font_data = bytes(header) + bytes(byte_data) + bytes(unicode_data)

    lines = [
        f'const uint8_t {identifier}[{len(font_data)}] '
        f'U8G2_FONT_SECTION("{identifier}") =',
    ]
    for offset in range(0, len(font_data), 16):
        chunk = font_data[offset : offset + 16]
        encoded = "".join(
            _escape_c_string_byte(
                value,
                chunk[index + 1] if index + 1 < len(chunk) else None,
            )
            for index, value in enumerate(chunk)
        )
        lines.append(f'  "{encoded}"')
    lines[-1] += ";"
    if source_header and not source_header.endswith(("\n", "\r")):
        source_header += "\n"
    return source_header + "\n".join(lines) + "\n"