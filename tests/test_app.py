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
    _description_codepoint,
    _parse_codepoint,
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

    def test_codepoint_input_accepts_common_hex_formats_and_unicode_scalars(self):
        self.assertEqual(_parse_codepoint("U+0041"), 0x41)
        self.assertEqual(_parse_codepoint("0x1f600"), 0x1F600)
        self.assertEqual(_parse_codepoint("2192"), 0x2192)
        self.assertIsNone(_parse_codepoint("U+D800"))
        self.assertIsNone(_parse_codepoint("110000"))
        self.assertIsNone(_parse_codepoint("not a codepoint"))

    def test_description_codepoint_supports_characters_and_u_plus_descriptions(self):
        self.assertEqual(_description_codepoint("A"), 0x41)
        self.assertEqual(_description_codepoint("😀"), 0x1F600)
        self.assertEqual(
            _description_codepoint("U+0041 5x8 x0 y-1 advance5"), 0x41
        )
        self.assertIsNone(_description_codepoint("letter A"))

    def test_pasted_codepoint_fills_an_empty_glyph_description(self):
        editor = PixelFontEditor.__new__(PixelFontEditor)
        editor.glyphs = [Glyph(1, 1)]
        editor.selected_index = 0
        editor._syncing_glyph_codepoint = False
        editor.glyph_codepoint_var = Mock()
        editor.glyph_codepoint_var.get.return_value = "U+1F600"
        editor.glyph_description_var = Mock()
        editor.glyph_unicode_name_var = Mock()

        editor._codepoint_changed()

        editor.glyph_description_var.set.assert_called_once_with("😀")
        editor.glyph_unicode_name_var.set.assert_called_once_with("GRINNING FACE")

    def test_single_character_description_updates_codepoint_field(self):
        editor = PixelFontEditor.__new__(PixelFontEditor)
        editor.glyphs = [Glyph(1, 1)]
        editor.selected_index = 0
        editor._syncing_glyph_description = False
        editor.glyph_description_var = Mock()
        editor.glyph_description_var.get.return_value = "é"
        editor.glyph_codepoint_var = Mock()
        editor.glyph_unicode_name_var = Mock()
        editor.glyph_list = Mock()
        editor._draw_sample_text = Mock()

        editor._description_changed()

        self.assertEqual(editor.selected_glyph.description, "é")
        editor.glyph_codepoint_var.set.assert_called_once_with("U+00E9")
        editor.glyph_unicode_name_var.set.assert_called_once_with(
            "LATIN SMALL LETTER E WITH ACUTE"
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

    def test_move_glyph_reorders_and_keeps_moved_glyph_selected(self):
        editor = PixelFontEditor.__new__(PixelFontEditor)
        first, second, third = (Glyph(1, 1) for _ in range(3))
        editor.glyphs = [first, second, third]
        editor.selected_index = 1
        editor._refresh = Mock()

        editor._move_glyph(1)

        self.assertIs(editor.glyphs[0], first)
        self.assertIs(editor.glyphs[1], third)
        self.assertIs(editor.glyphs[2], second)
        self.assertEqual(editor.selected_index, 2)
        editor._refresh.assert_called_once_with()

        editor._move_glyph(1)

        self.assertIs(editor.glyphs[0], first)
        self.assertIs(editor.glyphs[1], third)
        self.assertIs(editor.glyphs[2], second)
        self.assertEqual(editor.selected_index, 2)
        editor._refresh.assert_called_once_with()

        editor._move_glyph(-1)

        self.assertIs(editor.glyphs[0], first)
        self.assertIs(editor.glyphs[1], second)
        self.assertIs(editor.glyphs[2], third)
        self.assertEqual(editor.selected_index, 1)
        self.assertEqual(editor._refresh.call_count, 2)

    def test_select_glyph_refreshes_move_button_states(self):
        editor = PixelFontEditor.__new__(PixelFontEditor)
        editor.glyphs = [Glyph(1, 1) for _ in range(3)]
        editor.selected_index = 2
        editor.glyph_list = Mock()
        editor.move_up_button = Mock()
        editor.move_down_button = Mock()
        editor._refresh = Mock()

        editor.glyph_list.curselection.return_value = (0,)
        editor._select_glyph()

        editor.move_up_button.configure.assert_called_once_with(state="disabled")
        editor.move_down_button.configure.assert_called_once_with(state="normal")
        self.assertEqual(editor.selected_index, 0)
        editor._refresh.assert_called_once_with(refresh_glyph_list=False)

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

    def test_vt100_save_passes_selected_codepoint_to_c_export(self):
        editor = PixelFontEditor.__new__(PixelFontEditor)
        editor.root = Mock()
        editor.name_var = Mock()
        editor.name_var.get.return_value = "font_demo"
        editor.default_save_format = "VT100 font"
        editor.glyphs = [
            Glyph(1, 1, description="A"),
            Glyph(1, 1, description="↓"),
            Glyph(1, 1, description="U+0042 1x1 x0 y0 advance1"),
            Glyph(1, 1, description="HT"),
        ]
        editor.selected_index = 1
        editor.glyph_codepoint_var = Mock()
        editor.glyph_codepoint_var.get.return_value = "U+2193"
        editor.file_header = ""
        editor.status_var = Mock()

        with TemporaryDirectory() as directory:
            path = str(Path(directory) / "font_demo.c")
            with (
                patch(
                    "pixel_font_editor.app.filedialog.asksaveasfilename",
                    return_value=path,
                ),
                patch("pixel_font_editor.app.tk.StringVar") as make_string_var,
                patch("pixel_font_editor.app.render_c_font", return_value="output") as render,
                patch("builtins.open") as open_file,
            ):
                make_string_var.return_value.get.return_value = "VT100 font"
                editor._save()

        render.assert_called_once_with(
            "font_demo",
            editor.glyphs,
            header="",
            glyph_codepoints={0: 0x41, 1: 0x2193, 2: 0x42},
        )
        open_file.return_value.__enter__().write.assert_called_once_with("output")

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