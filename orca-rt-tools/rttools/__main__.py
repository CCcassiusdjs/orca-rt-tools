import sys
from pathlib import Path
from os import path

from rttools.terminal.terminal import error, header, info, warn, debug

from rttools.modules.io import configurator, appparser, nocparser, mapparser, svg, systemverilog
from rttools.modules.frequency import guesser, search
from rttools.modules.instances import instantiator
from rttools.modules.unwrapper import flowUnwrapper
from rttools.modules.backend.ags import ags, heuristics
from rttools.modules.backend.minizinc import minizinc
from rttools.modules.mapping import mapfile, spiral
from rttools.modules.routing import router

# the frequency search uses the AGS backend only (see
# rttools/modules/frequency/search.py)
RTTOOLS_ENABLE_MINIZINC = False

# value of <map> that selects the Spiral Mapping instead of a .map file
MAP_SPIRAL = "spiral"


# ==== Indrusiak params ===========
RTTOOLS_PRUNNING_FACTOR = 2000
RTTOOLS_FAIL_THRESHOULD = 500
#50k error tolerance
RTTOOLS_SCALING_TOLERANCE = 5000
RTTOOLS_DEFAULT_FREQUENCY = None
RTTOOLS_HEURISTIC = heuristics.mbcf
RTTOOLS_OPTIMIZE : bool = True
#SVG_SCALE = 0.01
SVG_SCALE = 0.1

# ==== brute force params
# RTTOOLS_PRUNNING_FACTOR = 1
# RTTOOLS_FAIL_THRESHOULD = 500
# RTTOOLS_SCALING_TOLERANCE = 0.01
# RTTOOLS_DEFAULT_FREQUENCY = 2000000
# RTTOOLS_HEURISTIC = heuristics.mbcf
# SVG_SCALE = 4.0

def parseMinimumReleaseTime(sched, p, hp):
    min = hp
    for ll in sched:
        print(ll)
        if ll[p] is not None and ll[p] < min:
            min = ll[p]
    return min


def parse_args(args):
    """Converts the positional arguments into a configuration.

    Ordem: <app> <map> <arch> [<freq>] [<pruning factor>]
    [<fail threshold>] [<optimize True|False>]. Argumentos ausentes
    receive the global values of the module. <map> is a .map file or
    the word `spiral` (MAP_SPIRAL)."""
    cfg = {
        "app_file": args[0],
        "map_file": args[1],
        "noc_file": args[2],
        "frequency": RTTOOLS_DEFAULT_FREQUENCY,
        "pruning_factor": RTTOOLS_PRUNNING_FACTOR,
        "fail_threshold": RTTOOLS_FAIL_THRESHOULD,
        "optimize": RTTOOLS_OPTIMIZE,
        "heuristic": RTTOOLS_HEURISTIC,
        "scaling_tolerance": RTTOOLS_SCALING_TOLERANCE,
    }
    if len(args) >= 4:
        cfg["frequency"] = int(args[3])
    if len(args) >= 5:
        cfg["pruning_factor"] = int(args[4])
    if len(args) >= 6:
        cfg["fail_threshold"] = int(args[5])
    if len(args) >= 7:
        cfg["optimize"] = (args[6] == "True")
    return cfg


def mesh_size(noc):
    """(width, height) of a mesh topology read by nocparser (node
    attributes X and Y)."""
    xs = [int(d["X"]) for _, d in noc.nodes(data=True)]
    ys = [int(d["Y"]) for _, d in noc.nodes(data=True)]
    return max(xs) + 1, max(ys) + 1


def load_mapping(map_arg, app, appname, noc, noc_file):
    """Mapping entries ({"node", "tasks"}) for the <map> argument: a .map
    file (rttools.modules.io.mapparser), or the word `spiral`, which runs
    ORT/GCM (criteria of Chapter 7, smallest deviation of the cluster WCET
    sums) and the Spiral Mapping (ORCA RT-Tools reference, Section 8.1.2) and saves the
    result as `<app>-SPIRAL-<arch>.map` in the current directory.

    Returns (entries, problems). `problems` lists a task on two nodes, a
    task out of the mapping and a node out of the architecture; a task of
    the file that the application does not have only gives a warning."""
    if map_arg == MAP_SPIRAL:
        width, height = mesh_size(noc)
        if width * height != noc.number_of_nodes():
            return None, ["spiral mapping needs a full mesh; `" + noc_file + "` has "
                          + str(noc.number_of_nodes()) + " nodes in " + str(width) + "x" + str(height)]
        tasks, edges = spiral.from_networkx(app)
        res = spiral.map_application(tasks, edges, width, height)
        for r in res["rows"]:
            info("GCM " + r["criterion"] + ": deviation " + str(round(r["sigma"], 3)) + "; "
                 + ", ".join(c + " (" + str(w) + ")" for c, w in zip(r["clusters"], r["wcet"])))
        info("Clustering criterion: " + res["criterion"])
        for c, node in sorted(res["cluster_nodes"].items(), key=lambda kv: kv[1]):
            info("Spiral mapping: " + c + " (volume " + str(res["volumes"][c]) + ") -> node " + str(node))
        entries = mapfile.from_dict(res["mapping"])
        out = appname + "-SPIRAL-" + Path(noc_file).stem + ".map"
        mapfile.write(out, entries)
        info("Mapping saved to `" + out + "`")
    else:
        info("Loading mapping file `" + map_arg + "`")
        entries = mapparser.loadFromFile(map_arg)
    # app or noc is None only when a test replaces the loaders
    tasks = list(app.nodes) if app is not None else None
    nodes = list(noc.nodes) if noc is not None else None
    if tasks is not None:
        for t in mapfile.unknown_tasks(entries or [], tasks):
            warn("Mapping: task " + t + " is not in the application (ignored)")
    return entries, mapfile.problems(entries or [], tasks, nodes)


def report_frequency(freq):
    """Prints f* (network, bisection), f_CPU (CPU test) and the minimum
    frequency max(f*, f_CPU) of search.minimum_frequency."""
    def hz(v):
        return "none" if v is None else str(v) + "Hz (" + format(v / 1e6, ".1f") + " MHz)"
    info("Network frequency f* = " + hz(freq["f_star_hz"]))
    if freq["cpu"] is not None:
        # general phase model (several periods or a cycle): demand per hyperperiod
        span = freq["cpu"].get("hyper_s", freq["cpu"]["period_s"])
        for node, d in sorted(freq["cpu"]["demand"].items(), key=lambda kv: str(kv[0])):
            info("CPU demand of node " + str(node) + ": " + str(d) + " cycles per "
                 + str(span) + " s")
    info("CPU frequency f_CPU = " + hz(freq["f_cpu_hz"]))
    chk = freq.get("final_check")
    if chk is not None:
        info("Network at f_CPU: " + ("feasible" if chk["feasible"] else "not feasible") + " ("
             + str(chk["packets"]) + " packets, " + str(chk["skipped"]) + " skipped, hyperperiod "
             + str(chk["hyperperiod"]) + " cycles)")
    if freq.get("final_search") is not None:
        info("First feasible frequency above f_CPU = " + hz(freq["frequency_hz"]))
    elif chk is not None and not chk["feasible"]:
        info("No feasible frequency above f_CPU")
    else:
        info("Minimum frequency max(f*, f_CPU) = " + hz(freq["frequency_hz"]))


def main():
    welcome_msg = '''
                                                                
    .-------------'```'----....,,__                        _,   
   |                               `'`'`'`'-.,.__        .'(    
   |                                             `'--._.'   )   
   |                                                   `'-.<    
   \               .-'`'-.                            -.    `\\ 
    \               -.o_.     _                     _,-'`\    | 
     ``````''--.._.-=-._    .'  \            _,,--'`      `-._( 
       (^^^^^^^^`___    '-. |    \  __,,..--'                 ` 
        `````````   `'--..___\    |`                            
                              `-.,'                             
                                                                 
 ORT: ORCA Realtime Tools
################################################################
'''

    header(welcome_msg)
    args = sys.argv[1:]
    # --costs <file>: static t(v) of rttools.wcet in place of the
    # Capacity column of the application (rttools/wcet/costs.py)
    from rttools.wcet import costs as wcosts
    try:
        args, costs_file = wcosts.split_flag(args)
    except wcosts.CostsError as e:
        error(str(e))
        return 1

    for i in args:
        info("-> " + i)

    # [0] application characterization
    # [1] mapping
    # [2] topology
    # [3] frequency
    if len(args) not in [3, 4, 5, 6, 7]:
        error("Usage: ")
        error("  __main__.py <app> <map> <arch> [<freq>] [<pruning factor>] [<fail threshold>] [<optimize True|False>]"
              " [--costs <costs.json>]")
        error("  <map>: mapping file (.map) or `" + MAP_SPIRAL + "` (ORT/GCM clustering and Spiral Mapping)")
        return 1

    # cfg_file = "rttools.ini"
    cfg = parse_args(args)
    app_file = cfg["app_file"]
    map_file = cfg["map_file"]
    noc_file = cfg["noc_file"]

    # local values; the module globals act as defaults
    RTTOOLS_DEFAULT_FREQUENCY = cfg["frequency"]
    RTTOOLS_PRUNNING_FACTOR = cfg["pruning_factor"]
    RTTOOLS_FAIL_THRESHOULD = cfg["fail_threshold"]
    RTTOOLS_OPTIMIZE = cfg["optimize"]
    RTTOOLS_HEURISTIC = cfg["heuristic"]
    RTTOOLS_SCALING_TOLERANCE = cfg["scaling_tolerance"]

    # parse configuration
    # info("Loading configuration file. `" + cfg_file + "`")
    # cfg = configurator.loadFromFile(cfg_file)

    info("Loading application file `" + app_file + "`")
    app, appname = appparser.loadFromFile(app_file)
    if costs_file is not None:
        info("Task costs t(v) = max(CSV, static WCET of `" + costs_file + "`) (rttools.wcet)")
        try:
            for label, (old, new) in sorted(wcosts.apply(app, costs_file).items()):
                info("  t(" + label + ") = " + str(new) + " cycles (application: " + str(old) + ")")
        except (wcosts.CostsError, OSError, ValueError) as e:
            error(str(e))
            return 1

    # print(app, appname)

    info("Loading NoC file `" + noc_file + "`")
    noc = nocparser.loadFromFile(noc_file)

    # link occupancy o_i = L0 + w_h (m + 1) + w_NI; w_h from RTTOOLS_HEADER_WAIT
    # (default HEADER_WAIT_CYCLES), w_NI from RTTOOLS_NI (default tt, NI_WAIT_CYCLES)
    try:
        w_h = router.header_wait()
    except ValueError as e:
        error(str(e) + " (" + router.HEADER_WAIT_ENV + ")")
        return 1
    try:
        ni_res, w_ni = router.ni_model()
    except ValueError as e:
        error(str(e) + " (" + router.NI_ENV + ")")
        return 1
    info("Link occupancy o_i = " + ("L0 + " + str(w_h) + " (m + 1)" if w_h else "L0")
         + (" + " + str(w_ni) if w_ni else "")
         + " (" + router.HEADER_WAIT_ENV + "; header wait bound " + str(router.HEADER_WAIT_CYCLES) + " cycles; "
         + router.NI_ENV + ": network interface " + ("as a resource, w_NI = " + str(w_ni) + " cycles" if ni_res
                                                     else "off") + ")")

    mapping, bad = load_mapping(map_file, app, appname, noc, noc_file)
    for p in bad:
        error("Mapping: " + p)
    if bad:
        return 1

    if RTTOOLS_DEFAULT_FREQUENCY is None:
        RTTOOLS_DEFAULT_FREQUENCY = guesser.guess()
        warn("No default frequency indicated, scaling for " + str(RTTOOLS_DEFAULT_FREQUENCY) + "Hz...")

    if RTTOOLS_OPTIMIZE == True:
        # CPU test once, outside the bisection; the bisection covers the
        # network only; the result is max(f*, f_CPU)
        freq = search.minimum_frequency(app, noc, mapping, appname, {
            "frequency": RTTOOLS_DEFAULT_FREQUENCY,
            "pruning_factor": RTTOOLS_PRUNNING_FACTOR,
            "fail_threshold": RTTOOLS_FAIL_THRESHOULD,
            "heuristic": RTTOOLS_HEURISTIC,
            "scaling_tolerance": RTTOOLS_SCALING_TOLERANCE,
        })
        result = freq["network"]

        if result is not None:
            warn("Unable to optmize minimum frequency any further.")
            info("Minimum frequency found at " + str(result["frequency"]) + "Hz")
            report_frequency(freq)

            debug(result["problem"]["packets"])

            filename = "results.svg"
            svg.saveSvg(
                filename, result["schedule"], result["problem"], result["skipped"], SVG_SCALE
            )
            info("Schedule visualization exported to `" + filename + "`")
        else:
            warn("Could not find a suitable frequency for the given flow set")
            report_frequency(freq)

    else:
        info("Target frequency is " + str(RTTOOLS_DEFAULT_FREQUENCY) + "Hz")
        cpu = search.cpu_check(app, mapping, noc)
        if cpu is not None:
            info("CPU test: f_CPU = " + str(cpu["f_cpu_hz"]) + "Hz; the target frequency "
                 + ("meets" if RTTOOLS_DEFAULT_FREQUENCY >= cpu["f_cpu_hz"] else "does not meet")
                 + " the CPU demand")
        result = search.schedule_at(app, noc, mapping, appname, RTTOOLS_DEFAULT_FREQUENCY, {
            "pruning_factor": RTTOOLS_PRUNNING_FACTOR,
            "fail_threshold": RTTOOLS_FAIL_THRESHOULD,
            "heuristic": RTTOOLS_HEURISTIC,
        })

        if result is None:
            error("Unable to find a hyperperiod value for the given flow set")
            return 1
        if result["schedule"] is None:
            error("Could not find a schedule at " + str(RTTOOLS_DEFAULT_FREQUENCY) + "Hz.")
            return 1

        app_file_path = Path(app_file)
        filename = path.join(app_file_path.parent, "results.svg")

        svg.saveSvg(
            filename, result["schedule"], result["problem"], result["skipped"], SVG_SCALE
        )

        info("Schedule visualization exported to `" + filename + "`")

    return 0


# Automatically jumps to main if called from command line.
# Executable script name is removed from the params list,
# and the list itself is passed to the real main() function.
if __name__ == "__main__":
    sys.exit(main())
