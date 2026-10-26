import unittest
from pathlib import Path

from pixel_font_editor.c_export import extract_c_header, parse_c_font, render_c_font
from pixel_font_editor.model import Glyph


class CExportTests(unittest.TestCase):
    def test_matches_font_t_initializer_shape(self):
        glyphs = [Glyph(4, 2, [0b1001, 0b0110]), Glyph(4, 2)]

        result = render_c_font("font_demo", glyphs)

        self.assertEqual(
            result,
            "const font_t font_demo = {\n"
            "    .width = 4,\n"
            "    .glyphs = {\n"
            "        // 0x00\n"
            "        0b1001,\n"
            "        0b0110,\n"
            "        // 0x01\n"
            "        0b0000,\n"
            "        0b0000,\n"
            "    }};\n",
        )

    def test_sanitizes_c_identifier(self):
        result = render_c_font("8x10 display", [Glyph(1, 1)])

        self.assertIn("const font_t font_8x10_display", result)

    def test_preserves_source_header_when_rendering(self):
        header = (
            "// Display font for the device\n"
            "#include \"font.h\"\n"
            "#include \"board_config.h\"\n\n"
        )

        result = render_c_font("font_demo", [Glyph(1, 1)], header=header)

        self.assertTrue(result.startswith(header))
        self.assertEqual(extract_c_header(result), header)

    def test_rejects_mismatched_glyph_dimensions(self):
        with self.assertRaises(ValueError):
            render_c_font("font_demo", [Glyph(2, 1), Glyph(3, 1)])

    def test_parse_round_trip_preserves_symbol_and_glyph_pixels(self):
        glyphs = [
            Glyph(4, 2, [0b1001, 0b0110], "Capital A"),
            Glyph(4, 2, description="Blank"),
        ]

        source = render_c_font("font_demo", glyphs)
        name, imported = parse_c_font(source)

        self.assertEqual(name, "font_demo")
        self.assertIn("// 0x00 Capital A", source)
        self.assertIn("// 0x01 Blank", source)
        self.assertEqual(
            [
                (glyph.width, glyph.height, glyph.rows, glyph.description)
                for glyph in imported
            ],
            [
                (glyph.width, glyph.height, glyph.rows, glyph.description)
                for glyph in glyphs
            ],
        )

    def test_parse_rejects_nonsequential_glyph_indices(self):
        source = render_c_font("font_demo", [Glyph(2, 1)]).replace("0x00", "0x02")

        with self.assertRaisesRegex(
            ValueError, r"expected 0x00, found 0x02 \(missing index 0x00"
        ):
            parse_c_font(source)

    def test_parse_reports_duplicate_glyph_index(self):
        source = render_c_font("font_demo", [Glyph(2, 1), Glyph(2, 1)])
        source = source.replace("// 0x01", "// 0x00")

        with self.assertRaisesRegex(
            ValueError, r"expected 0x01, found 0x00 \(duplicate index 0x00\)"
        ):
            parse_c_font(source)

    def test_parse_rejects_source_without_font_initializer(self):
        with self.assertRaisesRegex(ValueError, "initializer"):
            parse_c_font("int unrelated = 1;")

    def test_parse_sample_font_with_annotated_glyph_comments(self):
        sample_path = Path(__file__).parents[1] / "sample_files" / "font_8x10.c"

        name, glyphs = parse_c_font(sample_path.read_text(encoding="utf-8"))

        self.assertEqual(name, "font_8x10")
        self.assertEqual(len(glyphs), 136)
        self.assertTrue(all((glyph.width, glyph.height) == (8, 10) for glyph in glyphs))
        self.assertEqual(glyphs[0x80].description, "↓")


if __name__ == "__main__":
    unittest.main()