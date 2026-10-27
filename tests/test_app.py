import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pixel_font_editor.app import PixelFontEditor


class AppFormatTests(unittest.TestCase):
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