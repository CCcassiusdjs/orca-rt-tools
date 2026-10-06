"""Graph pane: GDE metrics, GCPA costs and critical path, layers, GCM
clustering."""
from __future__ import annotations

import os

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, DataTable, Input, Label, Select, Static, TabbedContent, TabPane

from rttools.tui.model import graphs
from rttools.tui.ui.dialogs import Field, FormDialog, guarded, parse_number
from rttools.tui.ui.tables import esc, fill


def draw_layers(graph, critical):
    """Columns of nodes by layer; critical path nodes in bold red, with the
    edges listed under the drawing."""
    layers = graphs.layers(graph)
    width = max((len(l) for layer in layers for l in layer), default=1) + 4
    height = max((len(l) for l in layers), default=0)
    out = []
    out.append("".join(f"L{i}".center(width) for i in range(len(layers))))
    for r in range(height):
        row = []
        for layer in layers:
            if r < len(layer):
                n = layer[r]
                cell = f"[{n}]".center(width)
                cell = esc(cell)
                if n in critical:
                    cell = "[b red]" + cell + "[/]"
                row.append(cell)
            else:
                row.append(" " * width)
        out.append("".join(row))
    out.append("")
    crit_edges = set(zip(critical, critical[1:]))
    for e in graph._edges:
        a, b = graphs.label(e._from), graphs.label(e._to)
        txt = esc(f"{a} → {b}  {int(e._data['payload']):,}")
        out.append(("[b red]" + txt + "[/]") if (a, b) in crit_edges else txt)
    return "\n".join(out)


class GraphPane(Widget):
    DEFAULT_CSS = """
    GraphPane { height: 1fr; }
    GraphPane #g-head { height: auto; padding: 0 1; background: $panel; }
    GraphPane #g-settings { height: 1; }
    GraphPane #g-settings Label { width: auto; }
    GraphPane #g-settings Input { width: 8; }
    GraphPane #g-settings Select { width: 14; }
    GraphPane #g-main { height: 1fr; }
    GraphPane #g-draw { width: 1fr; padding: 0 1; border-right: solid $panel; }
    GraphPane TabbedContent { width: 1fr; }
    GraphPane DataTable { height: 1fr; }
    """

    BINDINGS = [
        Binding("ctrl+o", "load", "Load graph"),
        Binding("ctrl+l", "cluster", "Cluster"),
        Binding("ctrl+s", "save", "Save clusters"),
    ]

    def __init__(self, **kw):
        super().__init__(**kw)
        self.graph = None
        self.path = None
        self.clustered = None

    def compose(self) -> ComposeResult:
        yield Static("No graph. ctrl+o loads a task graph in ORCA format (`# nodes` / `# edges`).", id="g-head")
        with Horizontal(id="g-settings"):
            yield Label(" Criterion ")
            yield Select([(c, c) for c in graphs.CRITERIA], value="MAX_PROC", allow_blank=False,
                         id="g-crit", compact=True)
            yield Label(" Clusters ")
            yield Input("4", id="g-n", compact=True)
            yield Button("Cluster", id="g-cluster", variant="primary", compact=True)
            yield Button("Save clustered", id="g-save", compact=True)
        with Horizontal(id="g-main"):
            with VerticalScroll(id="g-draw"):
                yield Static("", id="g-layers")
            with TabbedContent(id="g-tabs"):
                with TabPane("Nodes", id="g-tab-nodes"):
                    yield DataTable(id="g-nodes", cursor_type="row", zebra_stripes=True)
                with TabPane("Metrics", id="g-tab-metrics"):
                    yield DataTable(id="g-metrics", cursor_type="row")
                with TabPane("Clusters", id="g-tab-clusters"):
                    yield DataTable(id="g-clusters", cursor_type="row")

    def load(self, path):
        try:
            g = graphs.load(path)
        except Exception as exc:   # noqa: BLE001
            self.app.notify(f"{type(exc).__name__}: {exc}", severity="error", timeout=8)
            return False
        self.graph = g
        self.path = path
        self.clustered = None
        cost, path_nodes = graphs.gcpa(g)
        total = sum(int(n._data["wcet"]) for n in g._nodes)
        self.query_one("#g-head", Static).update(
            f"[b]{esc(os.path.basename(path))}[/b]  {len(g._nodes)} nodes, {len(g._edges)} edges, "
            f"WCET sum {total:,}; critical path (GCPA) {' → '.join(path_nodes)} = "
            f"{max(cost.values()) if cost else 0:,}")
        self.query_one("#g-layers", Static).update(draw_layers(g, path_nodes))
        layer_of = {}
        for i, layer in enumerate(graphs.layers(g)):
            for n in layer:
                layer_of[n] = i
        rows = []
        for n in g._nodes:
            lab = graphs.label(n)
            rows.append([lab, f"{int(n._data['wcet']):,}", layer_of.get(lab, "?"), f"{cost.get(lab, 0):,}",
                         "●" if lab in path_nodes else "",
                         " ".join(graphs.label(p) for p in graphs.preds(g, n)),
                         " ".join(graphs.label(s) for s in graphs.succs(g, n))])
        fill(self.query_one("#g-nodes", DataTable),
             ["Node", "WCET", "Layer", "GCPA cost", "Critical", "Predecessors", "Successors"], rows)
        fill(self.query_one("#g-metrics", DataTable), ["Metric (GDE)", "Value"],
             [[k, f"{v:,.4f}" if isinstance(v, float) else v] for k, v in graphs.metrics(g).items()])
        self.query_one("#g-clusters", DataTable).clear(columns=True)
        return True

    def on_button_pressed(self, event):
        if event.button.id == "g-cluster":
            self.action_cluster()
        elif event.button.id == "g-save":
            self.action_save()

    def action_load(self):
        def done(res):
            if res and res["path"]:
                self.load(res["path"])
        self.app.push_screen(FormDialog("Load task graph", [Field("path", "File", self.path or "", "path")]), guarded(self.app, done))

    def action_cluster(self):
        if self.graph is None:
            self.app.notify("load a graph first", severity="warning")
            return
        try:
            n = int(parse_number(self.query_one("#g-n", Input).value, 4))
        except ValueError:
            self.app.notify("number of clusters: integer", severity="error")
            return
        crit = self.query_one("#g-crit", Select).value
        cg = graphs.cluster(self.graph, n, crit)
        self.clustered = cg
        rows = graphs.cluster_rows(self.graph, cg)
        ccost, cpath = graphs.gcpa(cg)
        fill(self.query_one("#g-clusters", DataTable),
             ["Cluster", "Members", "WCET sum", "Payload inside", "Payload in", "Payload out", "GCPA cost",
              "Critical"],
             [[r["cluster"], len(r["members"]), f"{r['wcet']:,}", f"{r['inner']:,}", f"{r['in']:,}",
               f"{r['out']:,}", f"{ccost.get(r['cluster'], 0):,}", "●" if r["cluster"] in cpath else ""]
              for r in rows])
        self.query_one("#g-tabs", TabbedContent).active = "g-tab-clusters"
        self.app.notify(f"{crit}: {len(rows)} clusters")

    def action_save(self):
        if self.clustered is None:
            self.app.notify("cluster first", severity="warning")
            return
        crit = self.query_one("#g-crit", Select).value
        default = (self.path or "graph.txt").replace(".txt", ".clustered." + crit)

        def done(res):
            if res and res["path"]:
                graphs.save(res["path"], self.clustered)
                self.app.notify("saved " + res["path"])
        self.app.push_screen(FormDialog("Save clustered graph", [Field("path", "File", default, "path")]), guarded(self.app, done))
