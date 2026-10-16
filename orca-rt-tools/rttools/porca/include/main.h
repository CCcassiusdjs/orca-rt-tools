#include <iostream>

std::string WELCOME_MESSAGE[] = {

"      ⠀⠀⢀⣀⣀⣀⣀⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀                                        ",
"    ⠀⠀⠀⠺⢿⣿⣿⣿⣿⣿⣿⣷⣦⣠⣤⣤⣤⣄⣀⣀⠀⠀⠀⠀⠀⠀⠀⠀                                        ",
"    ⠀⠀⠀⠀⠀⠙⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣦⣄⠀⠀⠀                 Anonymous Lab              ",
"    ⠀⠀⠀⠀⢀⣴⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠿⠿⠿⣿⣿⣷⣄⠀⠀                                        ",
"   ⠀⠀⠀⠀⢠⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣀⠀⠀⠀⣀⣿⣿⣿⣆⠀                                        ",
"   ⠀⠀⠀⢠⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡄         ⠀Power-ORCA Environment for    ",
"   ⠀⠀⠀⣾⣿⣿⡿⠋⠁⣀⣠⣬⣽⣿⣿⣿⣿⣿⣿⠿⠿⠿⠿⠿⠿⠿⠿⠟⠁            Co-Scheduling Periodic,     ",
"   ⠀⠀⢀⣿⣿⡏⢀⣴⣿⠿⠛⠉⠉⠀⢸⣿⣿⠿⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀                Real-Time Tasks         ",
"  ⠀⠀⠀⢸⣿⣿⢠⣾⡟⠁⠀⠀⠀⠀⠀⠈⠉⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀              in Manycore Systems       ",
"     ⢸⣿⣿⣾⠏⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀                                                   ",
"     ⣸⣿⣿⣿⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀                                                 ",
"  ⠀⢠⣾⣿⣿⣿⣿⣿⣷⣄⠀⠀⠀⠀⠀⠀⠀    https://github.com/anonymous/porca        ",
"   ⣾⣿⣿⣿⣿⣿⣿⣿⣿⣦⠀⠀⠀⠀⠀⠀⠀                                                    ",
"  ⢰⣿⡿⠛⠉⠀⠀⠀⠈⠙⠛⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀                                                ",
"                                                                        " };

/*


# Parse application graph
# - tasks are <id, name, period, capacity, deadline, flows, cpu>
# - flows are <id, name, capacity, deadline, source, target>



# Generate task_occurences and packets
# - task_ocurrence is <id, task, name, release_time, abs_deadline, packets>
# - packets is <id, flow, minimum_release_time, abs_deadline>





# RTTOOLS_ENABLE_MINIZINC = False


# # ==== Indrusiak params ===========
# RTTOOLS_PRUNNING_FACTOR = 2000
# RTTOOLS_FAIL_THRESHOULD = 500
# RTTOOLS_SCALING_TOLERANCE = 0.01
# RTTOOLS_DEFAULT_FREQUENCY = None
# RTTOOLS_HEURISTIC = heuristics.mbcf
# RTTOOLS_OPTIMIZE : bool = True
# SVG_SCALE = 0.01

# # ==== brute force params
# # RTTOOLS_PRUNNING_FACTOR = 1
# # RTTOOLS_FAIL_THRESHOULD = 500
# # RTTOOLS_SCALING_TOLERANCE = 0.01
# # RTTOOLS_DEFAULT_FREQUENCY = 2000000
# # RTTOOLS_HEURISTIC = heuristics.mbcf
# # SVG_SCALE = 4.0

# def parseMinimumReleaseTime(sched, p, hp):
#     min = hp
#     for ll in sched:
#         print(ll)
#         if ll[p] is not None and ll[p] < min:
#             min = ll[p]
#     return min


# def main():
    

#     header(welcome_msg)
#     args = sys.argv[1:]

#     for i in args:
#         info("-> " + i)

#     # [0] application characterization
#     # [1] mapping
#     # [2] topology
#     # [3] frequency
#     if len(args) not in [3, 4, 5, 6, 7]:
#         error("Usage: ")
#         error("  __main__.py <app> <map> <arch> [<freq>] [<step>] [<tries>]")
#         return 1

#     # cfg_file = "rttools.ini"
#     app_file = args[0]
#     map_file = args[1]
#     noc_file = args[2]

#     if len(args) >= 4:
#         RTTOOLS_DEFAULT_FREQUENCY = int(args[3])

#     if len(args) >= 5:
#         RTTOOLS_PRUNNING_FACTOR = int(args[4])

#     if len(args) >= 6:
#         RTTOOLS_FAIL_THRESHOULD = int(args[5])

#     if len(args) >= 7:
#         if(args[6] == "True"):
#           RTTOOLS_OPTIMIZE = True
#         else:
#           RTTOOLS_OPTIMIZE = False
            

#     # parse configuration
#     # info("Loading configuration file. `" + cfg_file + "`")
#     # cfg = configurator.loadFromFile(cfg_file)

#     info("Loading application file `" + app_file + "`")
#     app, appname = appparser.loadFromFile(app_file)

#     info("Loading NoC file `" + noc_file + "`")
#     noc = nocparser.loadFromFile(noc_file)

#     info("Loading mapping file `" + map_file + "`")
#     mapping = mapparser.loadFromFile(map_file)

#     if RTTOOLS_DEFAULT_FREQUENCY is None:
#         RTTOOLS_DEFAULT_FREQUENCY = guesser.guess()
#         warn("No default frequency indicated, scaling for " + str(RTTOOLS_DEFAULT_FREQUENCY) + "Hz...")

#     schedule = None
#     pfreq = 0
#     nfreq = RTTOOLS_DEFAULT_FREQUENCY * 2
#     cfreq = RTTOOLS_DEFAULT_FREQUENCY

#     last_working_frequency = None
#     last_working_schedule = None
#     last_skipped_list = None
#     last_working_instance = None
#     last_working_hp = None

#     if RTTOOLS_OPTIMIZE == True: 

#       while True:
#           # generate instance
#           instance = instantiator.createInstance(app, noc, cfreq)
#           info("Tentative frequency is " + str(cfreq) + "Hz")

#           # unwrap flows into packets
#           packets, hp, nlinks = flowUnwrapper.unwrap(instance, noc, mapping)

#           if hp == 0:
#               break

#           # pre-tests here!
#           # testsres = prelaunchtest(problem)

#           # select which scheduler to use
#           if RTTOOLS_ENABLE_MINIZINC:
#               schedule = minizinc.minizincExport(
#                   packets, nlinks, hp, mapping, noc, appname
#               )
#           else:  # adaptive guided search
#               problem, schedule = ags.agsExport(
#                   packets,
#                   nlinks,
#                   hp,
#                   mapping,
#                   noc,
#                   appname,
#                   RTTOOLS_PRUNNING_FACTOR,
#                   RTTOOLS_FAIL_THRESHOULD,
#                   RTTOOLS_HEURISTIC,
#               )

#           # print(schedule)
#           if schedule is not None:
#               sched, skipped = schedule

#               if len(skipped) == 0:
#                   info(
#                       "Found a schedule at " + str(cfreq) + "Hz. Scaling frequency down."
#                   )
#                   last_working_frequency = cfreq
#                   last_working_schedule = sched
#                   last_skipped_list = skipped
#                   last_working_instance = instance
#                   last_working_hp = hp
#                   nfreq = cfreq
#               else:
#                   # unfeasible
#                   error("Could not find a schedule at " + str(cfreq) + "Hz.")
#                   error("Skip list is not empty (" + str(len(skipped)) + ")!")
#                   error("Scaling frequency up...")
#                   pfreq = cfreq

#           else:
#               # unfeasible
#               error("Could not find a schedule at " + str(cfreq) + "Hz.")
#               error("Scaling frequency up...")
#               pfreq = cfreq

#           cfreq = (nfreq + pfreq) / 2

#           if abs(pfreq - nfreq) < cfreq * RTTOOLS_SCALING_TOLERANCE:
#               break
          
#       if last_working_frequency is not None:
#           warn("Unable to optmize minimum frequency any further.")
#           info("Minimum frequency found at " + str(last_working_frequency) + "Hz")

#           debug(packets)

#           filename = "results.svg"
#           svg.saveSvg(
#               filename, last_working_schedule, problem, last_skipped_list, SVG_SCALE
#           )
#           info("Schedule visualization exported to `" + filename + "`")

#           expDir = "pkt-sim/packets"
#           systemverilog.exportPackets(
#               expDir, last_working_schedule, problem, last_working_frequency
#           )
#           systemverilog.genWaveform(expDir, noc)
#           systemverilog.genRunFile(expDir, hp)
#           info("SystemVerilog mimics exported to `" + expDir + "`")

#       else:
#           warn("Could not find a suitable frequency for the given flow set")

#     else:
#         # generate instance
#         instance = instantiator.createInstance(app, noc, RTTOOLS_DEFAULT_FREQUENCY)
#         info("Target frequency is " + str(cfreq) + "Hz")

#         # unwrap flows into packets
#         packets, hp, nlinks = flowUnwrapper.unwrap(instance, noc, mapping)

#         if hp == 0:
#           error("Unable to find a hyperperiod value for the given flow set")
#         else:
#           problem, schedule = ags.agsExport(
#             packets,
#             nlinks,
#             hp,
#             mapping,
#             noc,
#             appname,
#             RTTOOLS_PRUNNING_FACTOR,
#             RTTOOLS_FAIL_THRESHOULD,
#             RTTOOLS_HEURISTIC,
#           )

#         sched, skipped = schedule

#         filename = "results.svg"
#         svg.saveSvg(
#             filename, sched, problem, skipped, SVG_SCALE
#         )

#         info("Schedule visualization exported to `" + filename + "`")

#         expDir = "pkt-sim/packets"
#         systemverilog.exportPackets(
#             expDir, schedule, problem, RTTOOLS_DEFAULT_FREQUENCY
#         )
#         systemverilog.genWaveform(expDir, noc)
#         systemverilog.genRunFile(expDir, hp)
#         info("SystemVerilog mimics exported to `" + expDir + "`")

# # Automatically jumps to main if called from command line.
# # Executable script name is removed from the params list,
# # and the list itself is passed to the real main() function.
# if __name__ == "__main__":
#     main()


*/
