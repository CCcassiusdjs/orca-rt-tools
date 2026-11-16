"""DataTable filling with column widths from the content."""
from __future__ import annotations

from rich.text import Text

MAX_WIDTH = 80


def cell_len(c):
    return Text(str(c)).cell_len


def fill(table, headers, rows, keys=None):
    """Replaces columns and rows of `table`. Numeric-looking cells are right
    aligned."""
    rows = [[("" if c is None else c) for c in r] for r in rows]
    table.clear(columns=True)
    widths = [len(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = min(MAX_WIDTH, max(widths[i], cell_len(c)))
    for h, w in zip(headers, widths):
        table.add_column(h, width=w)
    for n, r in enumerate(rows):
        cells = []
        for c in r:
            s = str(c)
            if s and (s[0].isdigit() or s[0] in "-+") and any(ch.isdigit() for ch in s) and " to " not in s:
                cells.append(Text(s, justify="right"))
            else:
                # Text, not str: a str cell goes through markup and emoji
                # codes (":B:" in "A:B:D" became an emoji)
                cells.append(Text(s))
        table.add_row(*cells, key=None if keys is None else keys[n])


def esc(text):
    """Escapes Textual markup: every '[' becomes '\\['."""
    return str(text).replace("\\", "\\\\").replace("[", "\\[")
