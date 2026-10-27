import unittest
from pathlib import Path

from pixel_font_editor.model import Glyph
from pixel_font_editor.u8g2_export import render_u8g2_font
from pixel_font_editor.u8g2_import import (
    _extract_font_array,
    extract_u8g2_c_header,
    parse_u8g2_font,
    parse_u8g2_font_with_metadata,
)


class U8g2ImportTests(unittest.TestCase):
    def test_imports_provided_u8g2_icon_font(self):
        sample_path = Path(__file__).parents[1] / "sample_files" / "u8g2_font_m2icon_5_tf.c"

        name, glyphs = parse_u8g2_font(sample_path.read_text(encoding="utf-8"))

        self.assertEqual(name, "u8g2_font_m2icon_5_tf")
        self.assertEqual(len(glyphs), 24)
        self.assertEqual(
            (glyphs[0].width, glyphs[0].height, glyphs[0].rows),
            (
                9,
                6,
                [
                    0b000111000,
                    0b111111100,
                    0b100000100,
                    0b100000100,
                    0b111111100,
                    0,
                ],
            ),
        )
        self.assertEqual(glyphs[0].description, "U+0041 7x5 x0 y0 advance9")
        self.assertTrue(all((glyph.width, glyph.height) == (9, 6) for glyph in glyphs))
        self.assertTrue(all(glyph.width <= 32 and glyph.height <= 32 for glyph in glyphs))

    def test_imports_unsized_c_font_arrays(self):
        sample_path = Path(__file__).parents[1] / "sample_files" / "u8g2_font_m2icon_5_tf.c"
        source = sample_path.read_text(encoding="utf-8").replace("[225]", "[]", 1)

        name, glyphs = parse_u8g2_font(source)

        self.assertEqual(name, "u8g2_font_m2icon_5_tf")
        self.assertEqual(len(glyphs), 24)

    def test_decodes_5x8_font_rle_repeat_markers(self):
        sample_path = Path(__file__).parents[1] / "sample_files" / "u8g2_font_5x8_mr.c"

        name, glyphs = parse_u8g2_font(sample_path.read_text(encoding="utf-8"))

        self.assertEqual(name, "u8g2_font_5x8_mr")
        self.assertEqual(len(glyphs), 95)
        self.assertEqual(glyphs[0].description, "U+0020 5x8 x0 y-1 advance5")
        self.assertEqual(glyphs[0].rows, [0] * 8)
        self.assertEqual(glyphs[0x10].description[:7], "U+0030 ")
        self.assertEqual(glyphs[0x13].description[:7], "U+0033 ")
        self.assertEqual(glyphs[0x14].description[:7], "U+0034 ")
        self.assertEqual(glyphs[0x15].description[:7], "U+0035 ")

    def test_import_caches_font_rle_widths(self):
        sample_path = Path(__file__).parents[1] / "sample_files" / "u8g2_font_5x8_mr.c"

        name, glyphs, rle_widths = parse_u8g2_font_with_metadata(
            sample_path.read_text(encoding="utf-8")
        )

        self.assertEqual(name, "u8g2_font_5x8_mr")
        self.assertEqual(len(glyphs), 95)
        self.assertEqual(rle_widths[2:4], bytes((3, 2)))

    def test_rejects_source_without_u8g2_font_array(self):
        with self.assertRaisesRegex(ValueError, "U8g2 font string array"):
            parse_u8g2_font("const font_t unrelated = {};\n")

    def test_round_trips_bundled_u8g2_fonts(self):
        sample_dir = Path(__file__).parents[1] / "sample_files"
        for filename in ("u8g2_font_m2icon_5_tf.c", "u8g2_font_5x8_mr.c"):
            with self.subTest(filename=filename):
                name, original = parse_u8g2_font(
                    (sample_dir / filename).read_text(encoding="utf-8")
                )

                exported = render_u8g2_font(name, original)
                exported_name, imported = parse_u8g2_font(exported)

                self.assertEqual(exported_name, name)
                self.assertEqual(
                    [(glyph.description, glyph.rows) for glyph in imported],
                    [(glyph.description, glyph.rows) for glyph in original],
                )

    def test_export_uses_cached_rle_widths(self):
        sample_path = Path(__file__).parents[1] / "sample_files" / "u8g2_font_5x8_mr.c"
        source = sample_path.read_text(encoding="utf-8")
        name, glyphs, rle_widths = parse_u8g2_font_with_metadata(source)

        exported = render_u8g2_font(name, glyphs, font_header=rle_widths)
        exported_data = parse_u8g2_font_with_metadata(exported)
        imported_without_cache = render_u8g2_font(name, glyphs)
        recalculated_data = parse_u8g2_font_with_metadata(imported_without_cache)

        self.assertEqual(exported_data[2][2:4], bytes((3, 2)))
        self.assertNotEqual(recalculated_data[2][2:4], rle_widths[2:4])
        self.assertEqual(exported_data[2][1:17], rle_widths[1:17])
        self.assertLess(exported.count("\\"), len(_extract_font_array(exported)[1]))
        self.assertEqual(
            [(glyph.description, glyph.rows) for glyph in exported_data[1]],
            [(glyph.description, glyph.rows) for glyph in glyphs],
        )

    def test_round_trips_source_header_and_comments(self):
        sample_path = Path(__file__).parents[1] / "sample_files" / "u8g2_font_5x8_mr.c"
        source = sample_path.read_text(encoding="utf-8")
        header = extract_u8g2_c_header(source)
        name, glyphs, font_header = parse_u8g2_font_with_metadata(source)

        exported = render_u8g2_font(
            name,
            glyphs,
            font_header=font_header,
            source_header=header,
        )

        self.assertTrue(exported.startswith(header))
        self.assertEqual(extract_u8g2_c_header(exported), header)

    def test_round_trips_extended_unicode_glyphs(self):
        glyphs = [
            Glyph(2, 2, [0b10, 0b01], "U+0041 2x2 x-1 y0 advance3"),
            Glyph(2, 2, [0b11, 0b10], "U+0100 2x2 x0 y-1 advance2"),
        ]

        exported = render_u8g2_font("unicode_font", glyphs)
        name, imported = parse_u8g2_font(exported)

        self.assertIn('U8G2_FONT_SECTION("unicode_font")', exported)
        self.assertEqual(name, "unicode_font")
        self.assertEqual(
            [(glyph.description, glyph.rows) for glyph in imported],
            [(glyph.description, glyph.rows) for glyph in glyphs],
        )

    def test_assigns_printable_code_points_to_editor_glyphs(self):
        glyphs = [Glyph(2, 2, [0b10, 0b01], "custom A")]

        _, imported = parse_u8g2_font(render_u8g2_font("font", glyphs))

        self.assertEqual(imported[0].description, "U+0020 2x2 x0 y0 advance2")
        self.assertEqual(imported[0].rows, glyphs[0].rows)


if __name__ == "__main__":
    unittest.main()