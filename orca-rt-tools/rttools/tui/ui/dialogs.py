"""Form dialog used by all panes (open, export, unit, go to time)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.suggester import Suggester
from textual.widgets import Button, DirectoryTree, Input, Label, Select, Static, Switch


class PathSuggester(Suggester):
    """Completes the last component of a file system path."""

    def __init__(self):
        super().__init__(use_cache=False, case_sensitive=True)

    async def get_suggestion(self, value):
        if not value:
            return None
        path = os.path.expanduser(value)
        d, prefix = os.path.split(path)
        try:
            names = sorted(os.listdir(d or "."))
        except OSError:
            return None
        for n in names:
            if n.startswith(prefix) and n != prefix:
                full = os.path.join(d, n)
                if os.path.isdir(full):
                    full += os.sep
                if value.startswith("~"):
                    full = "~" + full[len(os.path.expanduser("~")):]
                return full
        return None


@dataclass
class Field:
    name: str
    label: str
    default: object = ""
    kind: str = "text"            # text, path, number, select, switch
    options: list = field(default_factory=list)   # (label, value) for select
    placeholder: str = ""


class FormDialog(ModalScreen):
    """Returns a dict name -> value, or None on cancel."""

    DEFAULT_CSS = """
    FormDialog { align: center middle; }
    FormDialog > Vertical { width: 96; max-width: 100%; height: auto; max-height: 90%;
        border: thick $accent; background: $surface; padding: 1 2; }
    FormDialog Grid { grid-size: 2; grid-columns: 22 1fr; grid-rows: auto; height: auto; grid-gutter: 0 1; }
    FormDialog Label { padding: 1 0 0 0; }
    FormDialog DirectoryTree { height: 14; border: round $panel; }
    FormDialog .buttons { height: auto; align-horizontal: right; padding-top: 1; }
    FormDialog .title { text-style: bold; padding-bottom: 1; }
    FormDialog .hint { color: $text-muted; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title, fields, hint="", tree_root=None):
        super().__init__()
        self.title_text = title
        self.fields = fields
        self.hint = hint
        self.tree_root = tree_root
        self._last_path = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self.title_text, classes="title")
            with Grid():
                for f in self.fields:
                    yield Label(f.label)
                    if f.kind == "select":
                        yield Select(f.options, value=f.default, allow_blank=False, id="f_" + f.name)
                    elif f.kind == "switch":
                        yield Switch(value=bool(f.default), id="f_" + f.name)
                    else:
                        yield Input(str(f.default) if f.default is not None else "",
                                    placeholder=f.placeholder, id="f_" + f.name,
                                    suggester=PathSuggester() if f.kind == "path" else None)
            if any(f.kind == "path" for f in self.fields):
                yield DirectoryTree(self.tree_root or os.getcwd())
            if self.hint:
                yield Static(self.hint, classes="hint")
            with Horizontal(classes="buttons"):
                yield Button("OK", variant="primary", id="ok")
                yield Button("Cancel", id="cancel")

    def on_mount(self):
        first = self.query("Input, Select, Switch").first()
        if first is not None:
            first.focus()

    def on_descendant_focus(self, event):
        w = event.widget
        if isinstance(w, Input) and w.id and any(f.kind == "path" and "f_" + f.name == w.id for f in self.fields):
            self._last_path = w

    def on_directory_tree_file_selected(self, event):
        target = self._last_path
        if target is None:
            for f in self.fields:
                if f.kind == "path":
                    target = self.query_one("#f_" + f.name, Input)
                    break
        if target is not None:
            target.value = str(event.path)
            target.focus()

    def on_input_submitted(self, event):
        self.action_ok()

    def on_button_pressed(self, event):
        if event.button.id == "ok":
            self.action_ok()
        else:
            self.action_cancel()

    def action_ok(self):
        out = {}
        for f in self.fields:
            w = self.query_one("#f_" + f.name)
            if f.kind == "select":
                out[f.name] = w.value
            elif f.kind == "switch":
                out[f.name] = w.value
            else:
                v = w.value.strip()
                if f.kind == "path":
                    v = os.path.expanduser(v)
                out[f.name] = v
        self.dismiss(out)

    def action_cancel(self):
        self.dismiss(None)


class TextDialog(ModalScreen):
    """Shows a block of text (help, errors, details)."""

    DEFAULT_CSS = """
    TextDialog { align: center middle; }
    TextDialog > Vertical { width: 110; max-width: 100%; height: auto; max-height: 90%;
        border: thick $accent; background: $surface; padding: 1 2; }
    TextDialog Static { height: auto; }
    """
    BINDINGS = [Binding("escape,enter,q", "close", "Close")]

    def __init__(self, title, text):
        super().__init__()
        self.title_text = title
        self.body = text

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("[b]" + self.title_text + "[/b]\n")
            yield Static(self.body, markup=False)
            yield Button("Close", id="close")

    def on_button_pressed(self, _):
        self.dismiss(None)

    def action_close(self):
        self.dismiss(None)


def guarded(app, callback):
    """Dialog callback that reports exceptions as notifications instead of
    ending the application."""
    def run(result):
        try:
            callback(result)
        except Exception as exc:   # noqa: BLE001 - shown to the user
            app.notify(f"{type(exc).__name__}: {exc}", severity="error", timeout=10)
    return run


def parse_number(text, default=None):
    """Integer or float from text with optional separators and SI suffix
    (k, M, G): '2M' -> 2000000, '1_000' -> 1000."""
    t = str(text).strip().replace("_", "").replace(",", "")
    if not t:
        return default
    mult = 1
    if t[-1] in "kKMG":
        mult = {"k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9}[t[-1]]
        t = t[:-1]
    v = float(t) * mult
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError("not a finite number: " + str(text))
    return int(v) if v == int(v) else v
