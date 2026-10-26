"""Bitmap glyph data model."""

from dataclasses import dataclass


MAX_DIMENSION = 32


@dataclass
class Glyph:
    """A glyph stored as one integer bitmask per row."""

    width: int
    height: int
    rows: list[int] | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if not 1 <= self.width <= MAX_DIMENSION:
            raise ValueError(f"width must be between 1 and {MAX_DIMENSION}")
        if not 1 <= self.height <= MAX_DIMENSION:
            raise ValueError(f"height must be between 1 and {MAX_DIMENSION}")
        if self.rows is None:
            self.rows = [0] * self.height
        elif len(self.rows) != self.height:
            raise ValueError("row count must match glyph height")
        elif any(row < 0 or row >= (1 << self.width) for row in self.rows):
            raise ValueError("row contains pixels outside glyph width")

    def is_pixel_on(self, x: int, y: int) -> bool:
        self._check_coordinates(x, y)
        return bool(self.rows[y] & (1 << (self.width - 1 - x)))

    def toggle_pixel(self, x: int, y: int) -> None:
        self._check_coordinates(x, y)
        self.rows[y] ^= 1 << (self.width - 1 - x)

    def resize(self, width: int, height: int) -> None:
        if not 1 <= width <= MAX_DIMENSION:
            raise ValueError(f"width must be between 1 and {MAX_DIMENSION}")
        if not 1 <= height <= MAX_DIMENSION:
            raise ValueError(f"height must be between 1 and {MAX_DIMENSION}")

        resized_rows = [0] * height
        for y in range(min(self.height, height)):
            for x in range(min(self.width, width)):
                if self.is_pixel_on(x, y):
                    resized_rows[y] |= 1 << (width - 1 - x)

        self.width = width
        self.height = height
        self.rows = resized_rows

    def _check_coordinates(self, x: int, y: int) -> None:
        if not 0 <= x < self.width or not 0 <= y < self.height:
            raise IndexError("pixel coordinates are outside the glyph")