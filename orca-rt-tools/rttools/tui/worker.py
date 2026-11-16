"""Child process of the network search (see model/network.py)."""
import json
import sys
import threading

from rttools.tui.model import network


def main():
    params = json.loads(sys.argv[1])
    out = sys.stdout
    lock = threading.Lock()

    def emit(kind, data):
        if kind == "result" and data is not None:
            data = network.encode_result(data)
        with lock:
            out.write(json.dumps({"kind": kind, "data": data}) + "\n")
            out.flush()

    network.run_worker(params, emit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
