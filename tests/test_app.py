import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from pixel_font_editor.app import (
    PixelFontEditor,
    TEMPLATE_DIR,
    _load_window_config,
    _glyph_index_for_character,
    _preview_pixel_scale,
    _render_unicode_glyphs,
    _wrap_sample_text,
)
from pixel_font_editor.model import Glyph


class AppFormatTests(unittest.TestCase):
    def test_window_config_loads_dimensions(self):
        with TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text(
                json.dumps({"window": {
                    "width": 1440,
                    "height": 900,
                    "min_width": 1200,
                    "min_height": 700,
                }}),
                encoding="utf-8",
            )

            self.assertEqual(
                _load_window_config(config_path), ((1440, 900), (1200, 700))
            )

    def test_missing_window_config_uses_defaults(self):
        with TemporaryDirectory() as directory:
            config_path = Path(directory) / "missing.json"

            self.assertEqual(
                _load_window_config(config_path), ((1380, 780), (1260, 640))
            )

    def test_sample_wrap_keeps_words_intact(self):
        self.assertEqual(
            _wrap_sample_text("the quick brown fox", 10),
            ["the quick", "brown fox"],
        )
        self.assertEqual(
            _wrap_sample_text("longword next", 4), ["longword", "next"]
        )
        self.assertEqual(_wrap_sample_text("", 10), [])

    def test_preview_pixel_scale_tracks_zoom_and_clamps_to_one_pixel(self):
        self.assertEqual(_preview_pixel_scale(8, 10, 215, 135, 0.3), 3)
        self.assertEqual(_preview_pixel_scale(8, 10, 215, 135, 0.7), 8)
        self.assertEqual(_preview_pixel_scale(8, 10, 215, 135, 0.01), 1)

    def test_sample_character_lookup_uses_format_specific_codepoints(self):
        vt100_glyphs = [Glyph(1, 1) for _ in range(0x42)]
        u8g2_glyphs = [
            Glyph(1, 1),
            Glyph(1, 1, description="U+0020 1x1 x0 y0 advance1"),
            Glyph(1, 1, description="U+0041 1x1 x0 y0 advance1"),
        ]

        self.assertEqual(
            _glyph_index_for_character(vt100_glyphs, "A", "VT100 font"), 0x41
        )
        self.assertEqual(
            _glyph_index_for_character(u8g2_glyphs, "A", "U8g2 font"), 2
        )
        self.assertIsNone(
            _glyph_index_for_character(u8g2_glyphs, "B", "U8g2 font")
        )

    def test_unicode_glyph_table_uses_descriptions_and_array_positions(self):
        glyphs = [Glyph(1, 1) for _ in range(0x82)]
        glyphs[0x7F].description = "U+2192 should be excluded"
        glyphs[0x80].description = "↓"
        glyphs[0x81].description = "U+2191 1x1 x0 y0 advance1"

        self.assertEqual(
            _render_unicode_glyphs(glyphs),
            "const font_unicode_glyph_t font_unicode_glyphs[] = {\n"
            '    {0x2193, 0x80, "↓"},\n'
            '    {0x2191, 0x81, "↑"},\n'
            "};",
        )

    def test_new_loads_the_starter_for_the_selected_format(self):
        cases = (
            ("VT100", "font_8x10.c"),
            ("u8g2", "u8g2_font_5x8_mr.c"),
        )
        for selected_format, sample_name in cases:
            with self.subTest(format=selected_format):
                editor = PixelFontEditor.__new__(PixelFontEditor)
                editor._choose_new_format = Mock(return_value=selected_format)
                editor._load_font = Mock()

                editor._new()

                editor._load_font.assert_called_once_with(str(TEMPLATE_DIR / sample_name))

    def test_new_blank_restores_the_application_starter(self):
        editor = PixelFontEditor.__new__(PixelFontEditor)
        editor._choose_new_format = Mock(return_value="Blank")
        editor.name_var = Mock()
        editor.width_var = Mock()
        editor.height_var = Mock()
        editor._refresh = Mock()
        editor.status_var = Mock()

        editor._new()

        self.assertEqual((editor.width, editor.height), (8, 10))
        self.assertEqual(len(editor.glyphs), 2)
        self.assertEqual(editor.glyphs[0].rows, [0] * 10)
        self.assertEqual(
            editor.glyphs[1].rows,
            [0b00010000, 0b00111000, 0b01111100, 0b11111110, 0b01111100,
             0b00111000, 0b00010000, 0, 0, 0],
        )
        self.assertEqual(editor.default_save_format, "VT100 font")
        self.assertIsNone(editor.u8g2_header)
        editor.name_var.set.assert_called_once_with("font_8x10")
        editor._refresh.assert_called_once_with()

    def test_save_cannot_overwrite_a_bundled_starter(self):
        editor = PixelFontEditor.__new__(PixelFontEditor)
        editor.root = Mock()
        editor.name_var = Mock()
        editor.name_var.get.return_value = "font_8x10"
        editor.default_save_format = "VT100 font"

        with (
            patch(
                "pixel_font_editor.app.filedialog.asksaveasfilename",
                return_value=str(TEMPLATE_DIR / "font_8x10.c"),
            ),
            patch("pixel_font_editor.app.tk.StringVar") as make_string_var,
            patch("pixel_font_editor.app.messagebox.showerror") as show_error,
            patch("builtins.open") as open_file,
        ):
            make_string_var.return_value.get.return_value = "VT100 font"
            editor._save()

        show_error.assert_called_once()
        open_file.assert_not_called()

    def test_save_defaults_to_the_format_of_the_opened_file(self):
        samples = Path(__file__).parents[1] / "sample_files"
        cases = (
            (samples / "font_5x10.c", "VT100 font"),
            (samples / "u8g2_font_m2icon_5_tf.c", "U8g2 font"),
        )

        for path, expected_format in cases:
            with self.subTest(format=expected_format):
                editor = PixelFontEditor.__new__(PixelFontEditor)
                editor.root = Mock()
                editor.name_var = Mock()
                editor.name_var.get.return_value = "test_font"
                editor.width_var = Mock()
                editor.height_var = Mock()
                editor.status_var = Mock()
                editor._refresh = Mock()

                with patch(
                    "pixel_font_editor.app.filedialog.askopenfilename",
                    return_value=str(path),
                ):
                    editor._open()

                selected_format = Mock()
                with (
                    patch(
                        "pixel_font_editor.app.tk.StringVar",
                        return_value=selected_format,
                    ) as make_string_var,
                    patch(
                        "pixel_font_editor.app.filedialog.asksaveasfilename",
                        return_value="",
                    ) as save_dialog,
                ):
                    editor._save()

                make_string_var.assert_called_once_with(value=expected_format)
                self.assertIs(
                    save_dialog.call_args.kwargs["typevariable"], selected_format
                )


if __name__ == "__main__":
    unittest.main()