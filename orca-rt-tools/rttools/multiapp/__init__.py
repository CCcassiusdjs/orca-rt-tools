"""Analysis flow for several periodic applications that share the NoC.

    python -m rttools.multiapp <composition.json> [--f0 <Hz>] [--out <dir>]
                               [--costs <application>=<costs.json> ...]

A composition places each application on its own set of PEs of one 2D
mesh; the applications share the routers and the links. The flow keeps
the analysis of one application (rttools/__main__.py, Section 6 of the
paper) per PE and builds one link schedule for the packets of all the
applications:

| Step | One application | Composition (rttools.multiapp.compose) |
|---|---|---|
| Mapping | .map file or Spiral Mapping on the whole mesh | .map file per application (node indices of the mesh), or the Spiral Mapping of each application on the next free nodes of the spiral, in the order of the composition; two applications on one PE are an error |
| CPU test | f_CPU = max_k t(V_k) / T | the same per application (its PEs, its period); f_CPU of the platform = the largest |
| Packet instance | packets of the flows over the hyperperiod of their periods | union of the packets of every application over the hyperperiod H of all periods |
| Link schedule | AGS on the packets of the application | AGS on the union; every packet on the NoC has a reservation, the condition of the header wait bound w_h (m + 1) |
| Frequency | max(f_NoC, f_CPU), network check at f_CPU | the same with f_NoC of the union and the largest f_CPU |
| Response | R_bound = n(v_last) T + F(v_last) / f | the same per application, with its own T at the frequency of the platform |

composition.json:

    {"arch": "<arch.gml>",
     "apps": [{"name": "<id>", "csv": "<app.csv>", "map": "<app.map>" | "spiral", "pes": <N>,
               "costs": "<costs.json>"}, ...]}

Paths are relative to the file. `pes` is the number of PEs of an
application with `map` = "spiral" (the number of clusters of ORT/GCM).
`costs` (optional; also --costs <name>=<file>) is a costs file of
rttools.wcet: the static t(v) replaces the Capacity column of the
application and its scheduler_cycles.

Several release periods or a cycle: when the applications have release
model phase and different task periods, or one application has several
periods or a cycle, the composition takes the general phase model of
rttools/bench_t/multirate.py on the union of the applications (phase P =
gcd of all periods, H = lcm; f_CPU,a from the ORT/BENCH sequences of the
PEs of a over H; packets of every job that sends; f = lowest frequency at
or above f_CPU with a feasible link schedule; response of each
application = largest data age over its cause-effect chains, R_bound for
an application with one period). The UCX-OS image of such a composition is
outside rttools.ucxgen compose, which needs one release period (one kernel
tick and one release generator period per image).
"""
