"""Tkinter interface for drawing and exporting bitmap fonts."""

from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from pixel_font_editor.c_export import extract_c_header, parse_c_font, render_c_font
from pixel_font_editor.model import Glyph, MAX_DIMENSION


ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"


class PixelFontEditor:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Pixel Font Editor")
        self._icon_image = tk.PhotoImage(file=str(ASSET_DIR / "pixel_font_editor.png"))
        self.root.iconphoto(True, self._icon_image)
        if sys.platform == "win32":
            self.root.iconbitmap(default=str(ASSET_DIR / "pixel_font_editor.ico"))
        self.root.geometry("1380x780")
        self.root.minsize(1260, 640)
        self.root.configure(background="#e8ece6")

        self.width = 8
        self.height = 10
        self.glyphs = [
            Glyph(self.width, self.height),
            Glyph(
                self.width,
                self.height,
                [
                    0b00010000,
                    0b00111000,
                    0b01111100,
                    0b11111110,
                    0b01111100,
                    0b00111000,
                    0b00010000,
                    0,
                    0,
                    0,
                ],
            ),
        ]
        self.selected_index = 0
        self.name_var = tk.StringVar(value="font_8x10")
        self.file_header = ""
        self.width_var = tk.IntVar(value=self.width)
        self.height_var = tk.IntVar(value=self.height)
        self.glyph_description_var = tk.StringVar()
        self._syncing_glyph_description = False
        self._paint_value: bool | None = None
        self._last_painted_cell: tuple[int, int] | None = None
        self.preview_zoom = tk.DoubleVar(value=0.3)
        self.preview_zoom_label = tk.StringVar(value="0.3x")
        self.status_var = tk.StringVar()

        self._configure_styles()
        self._build_layout()
        self.glyph_description_var.trace_add("write", self._description_changed)
        self._refresh()

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        style.configure("App.TFrame", background="#e8ece6")
        style.configure("Panel.TFrame", background="#f5f7f2")
        style.configure(
            "Eyebrow.TLabel",
            background="#e8ece6",
            foreground="#65746d",
            font=("TkDefaultFont", 9, "bold"),
        )
        style.configure(
            "Title.TLabel",
            background="#e8ece6",
            foreground="#183c38",
            font=("TkDefaultFont", 22, "bold"),
        )
        style.configure(
            "PanelTitle.TLabel",
            background="#f5f7f2",
            foreground="#183c38",
            font=("TkDefaultFont", 10, "bold"),
        )
        style.configure(
            "Status.TLabel",
            background="#183c38",
            foreground="#e5eee5",
            padding=(14, 8),
            font=("TkDefaultFont", 9),
        )

    def _build_layout(self) -> None:
        shell = ttk.Frame(self.root, style="App.TFrame", padding=(22, 18, 22, 14))
        shell.grid(row=0, column=0, sticky="nsew")
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(2, weight=1)

        header = ttk.Frame(shell, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        header.grid_columnconfigure(1, weight=1)
        ttk.Label(header, text="LCD TYPE / 01", style="Eyebrow.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(header, text="Pixel Font Editor", style="Title.TLabel").grid(
            row=1, column=0, sticky="w", pady=(2, 0)
        )
        export_area = ttk.Frame(header, style="App.TFrame")
        export_area.grid(row=1, column=1, sticky="e")
        ttk.Label(export_area, text="C SYMBOL", style="Eyebrow.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        ttk.Entry(export_area, textvariable=self.name_var, width=20).grid(
            row=1, column=0, padx=(0, 10), sticky="ew"
        )
        ttk.Button(export_area, text="Open .c", command=self._open).grid(
            row=1, column=1, sticky="e", padx=(0, 6)
        )
        ttk.Button(export_area, text="Save .c", command=self._export).grid(
            row=1, column=2, sticky="e"
        )

        ttk.Separator(shell).grid(row=1, column=0, sticky="ew", pady=(0, 14))

        work_area = ttk.Frame(shell, style="App.TFrame")
        work_area.grid(row=2, column=0, sticky="nsew")
        work_area.grid_rowconfigure(0, weight=1)
        work_area.grid_columnconfigure(0, minsize=190)
        work_area.grid_columnconfigure(1, weight=1, minsize=380)
        work_area.grid_columnconfigure(2, minsize=245)
        work_area.grid_columnconfigure(3, minsize=360)

        self._build_glyph_panel(work_area)
        self._build_grid_panel(work_area)
        self._build_preview_panel(work_area)
        self._build_glyph_atlas_panel(work_area)

        ttk.Label(
            shell,
            textvariable=self.status_var,
            style="Status.TLabel",
            anchor="w",
        ).grid(row=3, column=0, sticky="ew", pady=(14, 0))

    def _build_glyph_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=14)
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        ttk.Label(panel, text="GLYPHS", style="PanelTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 10)
        )

        list_frame = ttk.Frame(panel, style="Panel.TFrame")
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.glyph_list = tk.Listbox(
            list_frame,
            width=14,
            exportselection=False,
            activestyle="none",
            background="#ffffff",
            foreground="#263b37",
            selectbackground="#24695d",
            selectforeground="#ffffff",
            highlightthickness=0,
            borderwidth=0,
            font=("Menlo", 11),
        )
        self.glyph_list.grid(row=0, column=0, sticky="nsew")
        self.glyph_list.bind("<<ListboxSelect>>", self._select_glyph)
        list_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.glyph_list.yview)
        list_scroll.grid(row=0, column=1, sticky="ns")
        list_horizontal = ttk.Scrollbar(
            list_frame, orient="horizontal", command=self.glyph_list.xview
        )
        list_horizontal.grid(row=1, column=0, sticky="ew")
        self.glyph_list.configure(
            xscrollcommand=list_horizontal.set,
            yscrollcommand=list_scroll.set,
        )

        actions = ttk.Frame(panel, style="Panel.TFrame")
        actions.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        actions.grid_columnconfigure((0, 1), weight=1)
        ttk.Button(actions, text="+ Add", command=self._add_glyph).grid(
            row=0, column=0, columnspan=2, sticky="ew"
        )
        ttk.Button(actions, text="Remove", command=self._remove_glyph).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )

    def _build_grid_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=14)
        panel.grid(row=0, column=1, sticky="nsew", padx=5)
        panel.grid_rowconfigure(3, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        controls = ttk.Frame(panel, style="Panel.TFrame")
        controls.grid(row=0, column=0, sticky="ew")
        controls.grid_columnconfigure(0, weight=1)
        ttk.Label(controls, text="PIXEL GRID", style="PanelTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        dimensions = ttk.Frame(controls, style="Panel.TFrame")
        dimensions.grid(row=0, column=1, sticky="e")
        ttk.Label(dimensions, text="W", style="Eyebrow.TLabel").grid(row=0, column=0)
        self.width_input = ttk.Spinbox(
            dimensions,
            from_=1,
            to=MAX_DIMENSION,
            width=3,
            textvariable=self.width_var,
            command=self._apply_dimensions,
        )
        self.width_input.grid(row=0, column=1, padx=(4, 10))
        ttk.Label(dimensions, text="H", style="Eyebrow.TLabel").grid(row=0, column=2)
        self.height_input = ttk.Spinbox(
            dimensions,
            from_=1,
            to=MAX_DIMENSION,
            width=3,
            textvariable=self.height_var,
            command=self._apply_dimensions,
        )
        self.height_input.grid(row=0, column=3, padx=(4, 0))
        for widget in (self.width_input, self.height_input):
            widget.bind("<Return>", self._apply_dimensions)
            widget.bind("<FocusOut>", self._apply_dimensions)

        glyph_info = ttk.Frame(panel, style="Panel.TFrame")
        glyph_info.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        glyph_info.grid_columnconfigure(1, weight=1)
        ttk.Label(glyph_info, text="DESCRIPTION", style="Eyebrow.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 5)
        )
        ttk.Entry(glyph_info, textvariable=self.glyph_description_var).grid(
            row=0, column=1, sticky="ew"
        )

        ttk.Label(
            panel,
            text="Click a square to switch its pixel on or off.",
            background="#f5f7f2",
            foreground="#65746d",
        ).grid(row=2, column=0, sticky="w", pady=(10, 12))

        canvas_frame = ttk.Frame(panel, style="Panel.TFrame")
        canvas_frame.grid(row=3, column=0, sticky="nsew")
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)
        self.grid_canvas = tk.Canvas(
            canvas_frame,
            width=520,
            height=470,
            background="#f5f7f2",
            highlightthickness=0,
            borderwidth=0,
        )
        self.grid_canvas.grid(row=0, column=0, sticky="nsew")
        self.grid_canvas.bind("<Button-1>", self._start_paint)
        self.grid_canvas.bind("<B1-Motion>", self._continue_paint)
        self.grid_canvas.bind("<ButtonRelease-1>", self._finish_paint)
        horizontal = ttk.Scrollbar(
            canvas_frame, orient="horizontal", command=self.grid_canvas.xview
        )
        horizontal.grid(row=1, column=0, sticky="ew")
        vertical = ttk.Scrollbar(
            canvas_frame, orient="vertical", command=self.grid_canvas.yview
        )
        vertical.grid(row=0, column=1, sticky="ns")
        self.grid_canvas.configure(
            xscrollcommand=horizontal.set,
            yscrollcommand=vertical.set,
        )

    def _build_preview_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=14)
        panel.grid(row=0, column=2, sticky="nsew", padx=(10, 0))
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(2, weight=1)
        ttk.Label(panel, text="LIVE PREVIEW", style="PanelTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 7)
        )

        zoom_controls = ttk.Frame(panel, style="Panel.TFrame")
        zoom_controls.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        zoom_controls.grid_columnconfigure(1, weight=1)
        ttk.Label(zoom_controls, text="ZOOM", style="Eyebrow.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        ttk.Scale(
            zoom_controls,
            from_=0.1,
            to=1.0,
            variable=self.preview_zoom,
            command=self._set_preview_zoom,
        ).grid(row=0, column=1, sticky="ew")
        ttk.Label(
            zoom_controls,
            textvariable=self.preview_zoom_label,
            background="#f5f7f2",
            foreground="#183c38",
            width=5,
            anchor="e",
        ).grid(row=0, column=2, sticky="e", padx=(8, 0))

        preview_frame = ttk.Frame(panel, style="Panel.TFrame")
        preview_frame.grid(row=2, column=0, sticky="nsew")
        preview_frame.grid_rowconfigure(0, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)
        self.preview_canvas = tk.Canvas(
            preview_frame,
            width=215,
            height=240,
            background="#183c38",
            highlightthickness=0,
            borderwidth=0,
        )
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        self.preview_canvas.bind("<Configure>", self._preview_canvas_resized)
        preview_horizontal = ttk.Scrollbar(
            preview_frame, orient="horizontal", command=self.preview_canvas.xview
        )
        preview_horizontal.grid(row=1, column=0, sticky="ew")
        preview_vertical = ttk.Scrollbar(
            preview_frame, orient="vertical", command=self.preview_canvas.yview
        )
        preview_vertical.grid(row=0, column=1, sticky="ns")
        self.preview_canvas.configure(
            xscrollcommand=preview_horizontal.set,
            yscrollcommand=preview_vertical.set,
        )

        ttk.Label(panel, text="ROW DATA", style="PanelTitle.TLabel").grid(
            row=3, column=0, sticky="w", pady=(12, 7)
        )
        self.row_data = tk.Text(
            panel,
            width=18,
            height=8,
            background="#e9eee7",
            foreground="#26423c",
            font=("Menlo", 10),
            borderwidth=0,
            highlightthickness=0,
            padx=10,
            pady=8,
            state="disabled",
        )
        self.row_data.grid(row=4, column=0, sticky="ew")

    def _build_glyph_atlas_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=12)
        panel.grid(row=0, column=3, sticky="nsew", padx=(10, 0))
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        ttk.Label(panel, text="FONT ATLAS", style="PanelTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 10)
        )

        canvas_frame = ttk.Frame(panel, style="Panel.TFrame")
        canvas_frame.grid(row=1, column=0, sticky="nsew")
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)
        self.glyph_atlas_canvas = tk.Canvas(
            canvas_frame,
            width=340,
            height=500,
            background="#f5f7f2",
            highlightthickness=0,
            borderwidth=0,
        )
        self.glyph_atlas_canvas.grid(row=0, column=0, sticky="nsew")
        self.glyph_atlas_canvas.bind("<Button-1>", self._select_atlas_glyph)
        horizontal = ttk.Scrollbar(
            canvas_frame, orient="horizontal", command=self.glyph_atlas_canvas.xview
        )
        horizontal.grid(row=1, column=0, sticky="ew")
        vertical = ttk.Scrollbar(
            canvas_frame, orient="vertical", command=self.glyph_atlas_canvas.yview
        )
        vertical.grid(row=0, column=1, sticky="ns")
        self.glyph_atlas_canvas.configure(
            xscrollcommand=horizontal.set,
            yscrollcommand=vertical.set,
        )

    @property
    def selected_glyph(self) -> Glyph:
        return self.glyphs[self.selected_index]

    def _refresh(self, refresh_glyph_list: bool = True) -> None:
        if refresh_glyph_list:
            self._refresh_glyph_list()
        self._syncing_glyph_description = True
        self.glyph_description_var.set(self.selected_glyph.description)
        self._syncing_glyph_description = False
        self._draw_grid()
        self._draw_preview()
        self._draw_glyph_atlas()
        self._refresh_row_data()
        lit_pixels = sum(row.bit_count() for row in self.selected_glyph.rows) # type: ignore
        self.status_var.set(
            f"GLYPH 0x{self.selected_index:02X}   /   {len(self.glyphs):02d} TOTAL"
            f"                                      {lit_pixels} PIXELS ON"
        )

    def _description_changed(self, *_args: str) -> None:
        if self._syncing_glyph_description or not self.glyphs:
            return
        glyph = self.selected_glyph
        description = self.glyph_description_var.get()
        if glyph.description == description:
            return

        glyph.description = description
        self.glyph_list.delete(self.selected_index)
        self.glyph_list.insert(self.selected_index, self._glyph_list_label(self.selected_index))
        self.glyph_list.selection_set(self.selected_index)
        self.glyph_list.activate(self.selected_index)
        self.glyph_list.see(self.selected_index)

    def _glyph_list_label(self, index: int) -> str:
        description = " ".join(self.glyphs[index].description.split())
        suffix = f"  {description}" if description else ""
        return f"0x{index:02X}{suffix}"

    def _refresh_glyph_list(self) -> None:
        self.glyph_list.delete(0, tk.END)
        for index in range(len(self.glyphs)):
            self.glyph_list.insert(tk.END, self._glyph_list_label(index))
        self.glyph_list.selection_set(self.selected_index)
        self.glyph_list.activate(self.selected_index)
        self.glyph_list.see(self.selected_index)

    def _draw_grid(self) -> None:
        cell = min(42, max(16, 520 // max(self.width, self.height)))
        glyph = self.selected_glyph
        self.grid_canvas.delete("all")
        self.grid_canvas.configure(scrollregion=(0, 0, self.width * cell, self.height * cell))
        for y in range(self.height):
            for x in range(self.width):
                x0, y0 = x * cell, y * cell
                on = glyph.is_pixel_on(x, y)
                self.grid_canvas.create_rectangle(
                    x0,
                    y0,
                    x0 + cell,
                    y0 + cell,
                    fill="#df704d" if on else "#ffffff",
                    outline="#c8d2ca",
                    width=1,
                )

    def _draw_preview(self) -> None:
        glyph = self.selected_glyph
        self.preview_canvas.delete("all")
        canvas_width = max(1, self.preview_canvas.winfo_width())
        canvas_height = max(1, self.preview_canvas.winfo_height())
        fit_cell = max(3, min(22, (canvas_width - 20) // glyph.width,
                              (canvas_height - 20) // glyph.height))
        cell = max(2, round(fit_cell * self.preview_zoom.get()))
        content_width = glyph.width * cell
        content_height = glyph.height * cell
        scene_width = max(canvas_width, content_width)
        scene_height = max(canvas_height, content_height)
        left = (scene_width - content_width) // 2
        top = (scene_height - content_height) // 2
        self.preview_canvas.configure(scrollregion=(0, 0, scene_width, scene_height))
        for y in range(glyph.height):
            for x in range(glyph.width):
                if glyph.is_pixel_on(x, y):
                    x0, y0 = left + x * cell, top + y * cell
                    self.preview_canvas.create_rectangle(
                        x0,
                        y0,
                        x0 + cell,
                        y0 + cell,
                        fill="#d9e9a8",
                        outline="",
                    )

    def _draw_glyph_atlas(self) -> None:
        canvas = self.glyph_atlas_canvas
        canvas.delete("all")

        cell_width = max(18, self.width + 2)
        cell_height = max(22, self.height + 2)
        row_count = max(1, (len(self.glyphs) + 15) // 16)
        row_header_width = max(24, len(f"{(row_count - 1) * 16:X}") * 8 + 8)
        header_height = 20
        scene_width = row_header_width + 16 * cell_width
        scene_height = header_height + row_count * cell_height
        canvas.configure(scrollregion=(0, 0, scene_width, scene_height))

        for column in range(16):
            x = row_header_width + column * cell_width + cell_width / 2
            canvas.create_text(
                x,
                header_height / 2,
                text=f"{column:X}",
                fill="#65746d",
                font=("Menlo", 9, "bold"),
            )

        for row in range(row_count):
            y = header_height + row * cell_height
            canvas.create_text(
                row_header_width / 2,
                y + cell_height / 2,
                text=f"{row * 16:02X}",
                fill="#65746d",
                font=("Menlo", 9, "bold"),
            )

        for index, glyph in enumerate(self.glyphs):
            row, column = divmod(index, 16)
            x0 = row_header_width + column * cell_width
            y0 = header_height + row * cell_height
            selected = index == self.selected_index
            canvas.create_rectangle(
                x0,
                y0,
                x0 + cell_width,
                y0 + cell_height,
                fill="#183c38" if selected else "#ffffff",
                outline="#df704d" if selected else "#c8d2ca",
                width=2 if selected else 1,
            )

            pixel_scale = max(
                1,
                min(
                    2,
                    (cell_width - 2) // glyph.width,
                    (cell_height - 2) // glyph.height,
                ),
            )
            glyph_width = glyph.width * pixel_scale
            glyph_height = glyph.height * pixel_scale
            left = x0 + (cell_width - glyph_width) // 2
            top = y0 + (cell_height - glyph_height) // 2
            for glyph_y in range(glyph.height):
                for glyph_x in range(glyph.width):
                    if glyph.is_pixel_on(glyph_x, glyph_y):
                        pixel_x = left + glyph_x * pixel_scale
                        pixel_y = top + glyph_y * pixel_scale
                        canvas.create_rectangle(
                            pixel_x,
                            pixel_y,
                            pixel_x + pixel_scale,
                            pixel_y + pixel_scale,
                            fill="#d9e9a8" if selected else "#df704d",
                            outline="",
                        )

        canvas.after_idle(self._scroll_atlas_selection_into_view)

    def _scroll_atlas_selection_into_view(self) -> None:
        canvas = self.glyph_atlas_canvas
        if not canvas.winfo_exists() or not self.glyphs:
            return

        cell_width = max(18, self.width + 2)
        cell_height = max(22, self.height + 2)
        row_count = max(1, (len(self.glyphs) + 15) // 16)
        row_header_width = max(24, len(f"{(row_count - 1) * 16:X}") * 8 + 8)
        header_height = 20
        scene_width = row_header_width + 16 * cell_width
        scene_height = header_height + row_count * cell_height
        row, column = divmod(self.selected_index, 16)
        item_left = row_header_width + column * cell_width
        item_top = header_height + row * cell_height
        viewport_left = canvas.canvasx(0)
        viewport_top = canvas.canvasy(0)
        viewport_right = viewport_left + canvas.winfo_width()
        viewport_bottom = viewport_top + canvas.winfo_height()

        if item_left < viewport_left:
            canvas.xview_moveto(item_left / scene_width)
        elif item_left + cell_width > viewport_right:
            canvas.xview_moveto((item_left + cell_width - canvas.winfo_width()) / scene_width)
        if item_top < viewport_top:
            canvas.yview_moveto(item_top / scene_height)
        elif item_top + cell_height > viewport_bottom:
            canvas.yview_moveto((item_top + cell_height - canvas.winfo_height()) / scene_height)

    def _set_preview_zoom(self, value: str) -> None:
        self.preview_zoom_label.set(f"{float(value):.1f}x")
        self.preview_canvas.xview_moveto(0)
        self.preview_canvas.yview_moveto(0)
        self._draw_preview()

    def _preview_canvas_resized(self, _event: tk.Event) -> None:
        self._draw_preview()

    def _refresh_row_data(self) -> None:
        content = "\n".join(
            f"0b{row:0{self.width}b}" for row in self.selected_glyph.rows # type: ignore
        )
        self.row_data.configure(state="normal")
        self.row_data.delete("1.0", tk.END)
        self.row_data.insert("1.0", content)
        self.row_data.configure(state="disabled")

    def _grid_cell_at(self, event: tk.Event) -> tuple[int, int] | None:
        cell = min(42, max(16, 520 // max(self.width, self.height)))
        x = int(self.grid_canvas.canvasx(event.x) // cell)
        y = int(self.grid_canvas.canvasy(event.y) // cell)
        if 0 <= x < self.width and 0 <= y < self.height:
            return x, y
        return None

    def _start_paint(self, event: tk.Event) -> None:
        cell = self._grid_cell_at(event)
        if cell is None:
            return
        x, y = cell
        self._paint_value = not self.selected_glyph.is_pixel_on(x, y)
        self._last_painted_cell = cell
        self._paint_line(cell, cell)
        self._refresh(refresh_glyph_list=False)

    def _continue_paint(self, event: tk.Event) -> None:
        if self._paint_value is None:
            return
        cell = self._grid_cell_at(event)
        if cell is None:
            self._last_painted_cell = None
            return
        start = self._last_painted_cell or cell
        self._paint_line(start, cell)
        self._last_painted_cell = cell
        self._refresh(refresh_glyph_list=False)

    def _finish_paint(self, _event: tk.Event) -> None:
        self._paint_value = None
        self._last_painted_cell = None

    def _paint_line(self, start: tuple[int, int], end: tuple[int, int]) -> None:
        x, y = start
        end_x, end_y = end
        delta_x = abs(end_x - x)
        step_x = 1 if x < end_x else -1
        delta_y = -abs(end_y - y)
        step_y = 1 if y < end_y else -1
        error = delta_x + delta_y

        while True:
            if self.selected_glyph.is_pixel_on(x, y) != self._paint_value:
                self.selected_glyph.toggle_pixel(x, y)
            if x == end_x and y == end_y:
                break
            doubled_error = 2 * error
            if doubled_error >= delta_y:
                error += delta_y
                x += step_x
            if doubled_error <= delta_x:
                error += delta_x
                y += step_y

    def _select_glyph(self, _event: tk.Event | None = None) -> None:
        selection = self.glyph_list.curselection()
        if selection:
            self.selected_index = selection[0]
            self._refresh(refresh_glyph_list=False)

    def _select_atlas_glyph(self, event: tk.Event) -> None:
        canvas = self.glyph_atlas_canvas
        row_count = max(1, (len(self.glyphs) + 15) // 16)
        row_header_width = max(24, len(f"{(row_count - 1) * 16:X}") * 8 + 8)
        header_height = 20
        cell_width = max(18, self.width + 2)
        cell_height = max(22, self.height + 2)
        x = canvas.canvasx(event.x) - row_header_width
        y = canvas.canvasy(event.y) - header_height
        if x < 0 or y < 0:
            return

        column = int(x // cell_width)
        row = int(y // cell_height)
        index = row * 16 + column
        if 0 <= column < 16 and 0 <= index < len(self.glyphs):
            self.selected_index = index
            self._refresh()

    def _add_glyph(self) -> None:
        self.glyphs.append(Glyph(self.width, self.height))
        self.selected_index = len(self.glyphs) - 1
        self._refresh()

    def _duplicate_glyph(self) -> None:
        duplicate = Glyph(
            self.width,
            self.height,
            self.selected_glyph.rows.copy(), # type: ignore
            self.selected_glyph.description,
        )
        self.glyphs.insert(self.selected_index + 1, duplicate)
        self.selected_index += 1
        self._refresh()

    def _remove_glyph(self) -> None:
        if len(self.glyphs) == 1:
            self.status_var.set("A font must contain at least one glyph.")
            return
        del self.glyphs[self.selected_index]
        self.selected_index = min(self.selected_index, len(self.glyphs) - 1)
        self._refresh()

    def _apply_dimensions(self, _event: tk.Event | None = None) -> None:
        try:
            width = int(self.width_var.get())
            height = int(self.height_var.get())
            if not 1 <= width <= MAX_DIMENSION or not 1 <= height <= MAX_DIMENSION:
                raise ValueError
        except (ValueError, tk.TclError):
            self.width_var.set(self.width)
            self.height_var.set(self.height)
            self.status_var.set(f"Grid dimensions must be between 1 and {MAX_DIMENSION}.")
            return

        if width == self.width and height == self.height:
            return
        self.width, self.height = width, height
        for glyph in self.glyphs:
            glyph.resize(width, height)
        self._refresh()

    def _open(self) -> None:
        path = filedialog.askopenfilename(
            title="Open C font",
            filetypes=[("C source", "*.c"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as file:
                source = file.read()
            name, glyphs = parse_c_font(source)
            file_header = extract_c_header(source)
        except (OSError, ValueError) as error:
            messagebox.showerror("Could not open font", str(error), parent=self.root)
            return

        self.name_var.set(name)
        self.file_header = file_header
        self.glyphs = glyphs
        self.width = glyphs[0].width
        self.height = glyphs[0].height
        self.width_var.set(self.width)
        self.height_var.set(self.height)
        self.selected_index = 0
        self._refresh()
        self.status_var.set(f"Opened {len(glyphs)} glyphs from {path}")

    def _export(self) -> None:
        suggested_name = self.name_var.get().strip() or "font"
        path = filedialog.asksaveasfilename(
            title="Export C font",
            defaultextension=".c",
            initialfile=f"{suggested_name}.c",
            filetypes=[("C source", "*.c"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            output = render_c_font(
                suggested_name,
                self.glyphs,
                header=self.file_header,
            )
            with open(path, "w", encoding="utf-8", newline="\n") as file:
                file.write(output)
        except (OSError, ValueError) as error:
            messagebox.showerror("Export failed", str(error), parent=self.root)
            return
        self.status_var.set(f"Exported {len(self.glyphs)} glyphs to {path}")


def run() -> None:
    root = tk.Tk()
    PixelFontEditor(root)
    root.mainloop()