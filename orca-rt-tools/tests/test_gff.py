"""Fix 7 (rttools/gff/__main__.py).

1. `raise error(...)`: `error` was not imported (NameError) and, even
   if imported, returns None (TypeError).
2. ORCA -> ORCA called orca_export(graph, ofile), but the signature is
   export_graph(filename, graph).
"""
import os

import pytest

from tests.conftest import REPO_ROOT
from rttools.gff.__main__ import convert_graph
from rttools.gff.orca import import_graph

SRC = os.path.join(REPO_ROOT, "apps", "sample-graph-a", "sample_graph.txt")


def test_invalid_input_format_raises_valueerror(tmp_path):
    with pytest.raises(ValueError):
        convert_graph(SRC, "XYZ", "ORCA", str(tmp_path / "o.txt"))


def test_invalid_output_format_raises_valueerror(tmp_path):
    with pytest.raises(ValueError):
        convert_graph(SRC, "ORCA", "XYZ", str(tmp_path / "o.txt"))


def test_orca_to_orca_roundtrip(tmp_path):
    out = tmp_path / "o.txt"
    convert_graph(SRC, "ORCA", "ORCA", str(out))
    a, b = import_graph(SRC), import_graph(str(out))
    assert [n._data for n in a._nodes] == [n._data for n in b._nodes]
    assert [(e._from._data["label"], e._to._data["label"], e._data["payload"]) for e in a._edges] == \
           [(e._from._data["label"], e._to._data["label"], e._data["payload"]) for e in b._edges]


def test_orca_to_dot(tmp_path):
    out = tmp_path / "o.dot"
    convert_graph(SRC, "ORCA", "DOT", str(out))
    text = out.read_text()
    assert text.startswith("digraph {")
    assert '"A" -> "C"' in text
