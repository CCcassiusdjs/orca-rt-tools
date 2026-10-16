"""Static WCET analysis of the programs of the HF-RISC PEs (ORCA platform,
UCX-OS) and the task costs t(v) of the analysis flow.

| Module | Content |
|---|---|
| decode | RV32I/RV32E decoder |
| image | program image from an ELF file or an objdump listing |
| timing | cycles per instruction of the HF-RISC core |
| cfg | basic blocks, dominators and natural loops |
| value | constant propagation (arguments of calls, branch outcomes, counted loops) |
| loopbound | counted loops and bound expressions |
| annotations | loop bounds, indirect targets and excluded calls of a JSON file |
| ipet | IPET as an integer linear program (scipy.optimize.milp) |
| analysis | WCET of functions, segments and task jobs |
| ucx | t(v) of a UCX-OS task: job, dispatch, send and receive per edge, tick and release handlers |
| costs | t(v) files and their use by the analysis flow |

    python -m rttools.wcet analyze <image> --spec <spec.json> [--out <costs.json>]
    python -m rttools.wcet function <image> <function> [--arg a0=N ...] [--annotations FILE ...]
"""
