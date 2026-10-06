import sys
from pathlib import Path
from os import path

from rttools.terminal.terminal import error, header, info, warn, debug

from rttools.modules.io import configurator, appparser, nocparser, mapparser, svg, systemverilog
from rttools.modules.frequency import guesser
from rttools.modules.instances import instantiator
from rttools.modules.unwrapper import flowUnwrapper
from rttools.modules.backend.ags import ags, heuristics
from rttools.modules.backend.minizinc import minizinc

RTTOOLS_ENABLE_MINIZINC = False


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
    receive the global values of the module."""
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

    for i in args:
        info("-> " + i)

    # [0] application characterization
    # [1] mapping
    # [2] topology
    # [3] frequency
    if len(args) not in [3, 4, 5, 6, 7]:
        error("Usage: ")
        error("  __main__.py <app> <map> <arch> [<freq>] [<pruning factor>] [<fail threshold>] [<optimize True|False>]")
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

    # print(app, appname)

    info("Loading NoC file `" + noc_file + "`")
    noc = nocparser.loadFromFile(noc_file)

    info("Loading mapping file `" + map_file + "`")
    mapping = mapparser.loadFromFile(map_file)

    if RTTOOLS_DEFAULT_FREQUENCY is None:
        RTTOOLS_DEFAULT_FREQUENCY = guesser.guess()
        warn("No default frequency indicated, scaling for " + str(RTTOOLS_DEFAULT_FREQUENCY) + "Hz...")

    schedule = None


    low_frequency = 0
    center_frequency = RTTOOLS_DEFAULT_FREQUENCY
    upper_frequency = RTTOOLS_DEFAULT_FREQUENCY * 10

    last_working_frequency = None
    last_working_schedule = None
    last_skipped_list = None
    last_working_instance = None
    last_working_hp = None

    if RTTOOLS_OPTIMIZE == True: 

      while True:
          # generate instance
          instance = instantiator.createInstance(app, noc, center_frequency)
          info("Tentative frequency is " + str(center_frequency) + "Hz")

          # print(instance)

          # unwrap flows into packets
          packets, hp, nlinks = flowUnwrapper.unwrap(instance, noc, mapping)

          if hp == 0:
              break

          # pre-tests here!
          # testsres = prelaunchtest(problem)

          # select which scheduler to use
          if RTTOOLS_ENABLE_MINIZINC:
              schedule = minizinc.minizincExport(
                  packets, nlinks, hp, mapping, noc, appname
              )
          else:  # adaptive guided search
              problem, schedule = ags.agsExport(
                  packets,
                  nlinks,
                  hp,
                  mapping,
                  noc,
                  appname,
                  RTTOOLS_PRUNNING_FACTOR,
                  RTTOOLS_FAIL_THRESHOULD,
                  RTTOOLS_HEURISTIC,
              )

          # print(schedule)
          if schedule is not None:
              sched, skipped = schedule

              if len(skipped) == 0:
                  warn(
                      "Found a schedule at " + str(center_frequency) + "Hz. Scaling frequency down."
                  )
                  last_working_frequency = center_frequency
                  last_working_schedule = sched
                  last_skipped_list = skipped
                  last_working_instance = instance
                  last_working_hp = hp
                  
                  upper_frequency = center_frequency
                  center_frequency = (upper_frequency + low_frequency) / 2
              else:
                  # unfeasible
                  error("Could not find a schedule at " + str(center_frequency) + "Hz.")
                  error("Skip list is not empty (" + str(len(skipped)) + ")!")
                  error("Scaling frequency up...")
                  upper_frequency = center_frequency * 2
                  low_frequency = center_frequency
                  center_frequency = (upper_frequency + low_frequency) / 2
                  

          else:
              # unfeasible
              error("Could not find a schedule at " + str(center_frequency) + "Hz.")
              error("Scaling frequency up...")
              upper_frequency = center_frequency * 2
              low_frequency = center_frequency
              center_frequency = (upper_frequency + low_frequency) / 2

          if (upper_frequency - low_frequency) < RTTOOLS_SCALING_TOLERANCE:
              break
          
      if last_working_frequency is not None:
          warn("Unable to optmize minimum frequency any further.")
          info("Minimum frequency found at " + str(last_working_frequency) + "Hz")

          debug(packets)

          filename = "results.svg"
          svg.saveSvg(
              filename, last_working_schedule, problem, last_skipped_list, SVG_SCALE
          )
          info("Schedule visualization exported to `" + filename + "`")

          # expDir = "pkt-sim/packets"
          # systemverilog.exportPackets(
          #     expDir, last_working_schedule, problem, last_working_frequency
          # )
          # systemverilog.genWaveform(expDir, noc)
          # systemverilog.genRunFile(expDir, hp)
          # info("SystemVerilog mimics exported to `" + expDir + "`")

      else:
          warn("Could not find a suitable frequency for the given flow set")

    else:
        # generate instance
        instance = instantiator.createInstance(app, noc, RTTOOLS_DEFAULT_FREQUENCY)
        info("Target frequency is " + str(center_frequency) + "Hz")

        # unwrap flows into packets
        packets, hp, nlinks = flowUnwrapper.unwrap(instance, noc, mapping)

        if hp == 0:
          error("Unable to find a hyperperiod value for the given flow set")
          return 1
        else:
          problem, schedule = ags.agsExport(
            packets,
            nlinks,
            hp,
            mapping,
            noc,
            appname,
            RTTOOLS_PRUNNING_FACTOR,
            RTTOOLS_FAIL_THRESHOULD,
            RTTOOLS_HEURISTIC,
          )

        sched, skipped = schedule

        app_file_path = Path(app_file)
        filename = path.join(app_file_path.parent, "results.svg")
        
        svg.saveSvg(
            filename, sched, problem, skipped, SVG_SCALE
        )

        info("Schedule visualization exported to `" + filename + "`")

        # expDir = "pkt-sim/packets"
        # systemverilog.exportPackets(
        #     expDir, schedule, problem, RTTOOLS_DEFAULT_FREQUENCY
        # )
        # systemverilog.genWaveform(expDir, noc)
        # systemverilog.genRunFile(expDir, hp)
        # info("SystemVerilog mimics exported to `" + expDir + "`")

# Automatically jumps to main if called from command line.
# Executable script name is removed from the params list,
# and the list itself is passed to the real main() function.
if __name__ == "__main__":
    sys.exit(main())
