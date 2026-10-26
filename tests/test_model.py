import unittest

from pixel_font_editor.model import Glyph


class GlyphTests(unittest.TestCase):
    def test_toggle_uses_leftmost_bit_for_first_column(self):
        glyph = Glyph(4, 2)

        glyph.toggle_pixel(0, 0)
        glyph.toggle_pixel(3, 1)

        self.assertEqual(glyph.rows, [0b1000, 0b0001])
        self.assertTrue(glyph.is_pixel_on(0, 0))
        self.assertFalse(glyph.is_pixel_on(1, 0))

    def test_resize_preserves_pixels_by_coordinate(self):
        glyph = Glyph(3, 2, [0b101, 0b010])

        glyph.resize(4, 3)

        self.assertEqual(glyph.rows, [0b1010, 0b0100, 0b0000])

    def test_rejects_pixels_outside_dimensions(self):
        with self.assertRaises(IndexError):
            Glyph(2, 2).toggle_pixel(2, 0)


if __name__ == "__main__":
    unittest.main()