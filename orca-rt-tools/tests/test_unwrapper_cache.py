"""flowUnwrapper kept the GCPA table of the first application in a module
variable: a second application in the same process failed with KeyError
(or used the costs of the first one when task ids coincide)."""
import os
import subprocess
import sys
import json

from tests.conftest import REPO_ROOT, PKG_ROOT
from rttools.tui.model import network

DCT = [os.path.join(REPO_ROOT, "apps", "str2rts-dct-verify", f) for f in
       ("DCT-Verify.csv", "STR2RST-DCT-verify-ONTO-hermes3x2.map")] + [os.path.join(REPO_ROOT, "arch", "hermes-2x3.gml")]
SYN = [os.path.join(REPO_ROOT, "apps", "synthetic-flow-d", f) for f in
       ("SyntheticD.csv", "Synthetic-Flow-D-ONTO-hermes4x4.map")] + [os.path.join(REPO_ROOT, "arch", "hermes-4x4.gml")]


def packets_of(files):
    rows, hp, packets = network.flows_at(network.load_case(*files), 2000000)
    return [(p["name"], p["min_start"], p["abs_deadline"]) for p in packets]


def fresh(files):
    code = ("import sys, json; sys.path.insert(0, %r)\n"
            "from tests.test_unwrapper_cache import packets_of\n"
            "print(json.dumps(packets_of(%r)))" % (PKG_ROOT, files))
    out = subprocess.run([sys.executable, "-c", code], cwd=PKG_ROOT, capture_output=True, text=True, check=True)
    return [tuple(x) for x in json.loads(out.stdout)]


def test_two_applications_in_one_process():
    packets_of(SYN)
    assert packets_of(DCT) == fresh(DCT)
    assert packets_of(SYN) == fresh(SYN)
