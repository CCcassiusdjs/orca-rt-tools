from rttools.terminal.terminal import warn, info, debug
import glob
import os


def genRunFile(expDir, hp):
    filename = expDir + "/mockup.run.do"
    grep_run_files = glob.glob(expDir + "/*.run.do")

    for file in grep_run_files:
        warn("Removing outdated file `" + file + "`")
        os.unlink(file)

    # 100 comes from the initial delay
    # 100 more to generate scrolling after the wave body
    debug("exported run for ", hp, " ns")
    ss = "run " + str(hp + 200) + "ns"

    file = open(filename, "w")
    file.write(ss)
    file.close()
    info("Generating `" + filename + "`")


def genWaveform(expDir, noc):
    # noc_top_mod_name = "{noc_top_mod_name}"
    noc_top_mod_name = "manycore_top"

    ss = "onerror {resume}\n"
    ss += "quietly WaveActivateNextPane {} 0\n"
    ss += f"add wave -noupdate /{noc_top_mod_name}/clock\n"
    ss += f"add wave -noupdate /{noc_top_mod_name}/reset\n"

    for n in noc.nodes(data=True):
        node, data = n
        x, y = data

        x = data["X"]
        y = data["Y"]

        ss += f"add wave -noupdate -divider {{Node {x}-{y}}}\n"

        ss += f"add wave -noupdate -expand -group {x}{y}_perif {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/perif_if/clock}}\n"
        ss += f"add wave -noupdate -expand -group {x}{y}_perif {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/perif_if/reset}}\n"
        ss += f"add wave -noupdate -expand -group {x}{y}_perif {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/perif_if/addr_in}}\n"
        ss += f"add wave -noupdate -expand -group {x}{y}_perif {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/perif_if/data_in}}\n"
        ss += f"add wave -noupdate -expand -group {x}{y}_perif {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/perif_if/data_out}}\n"
        ss += f"add wave -noupdate -expand -group {x}{y}_perif {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/perif_if/sel_in}}\n"
        ss += f"add wave -noupdate -expand -group {x}{y}_perif {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/perif_if/wr_in}}\n"
        ss += f"add wave -noupdate -expand -group {x}{y}_perif {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/perif_if/irq}}\n"
        ss += f"add wave -noupdate -expand -group {x}{y}_perif {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/perif_if/gpioa_in}}\n"
        ss += f"add wave -noupdate -expand -group {x}{y}_perif {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/perif_if/gpioa_out}}\n"
        ss += f"add wave -noupdate -expand -group {x}{y}_perif {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/perif_if/gpioa_ddr}}\n"

        ss += f"add wave -noupdate -group {x}{y}_ddma_state -radix decimal {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/ddma_mod/temp_addr_in}}\n"
        ss += f"add wave -noupdate -group {x}{y}_ddma_state -radix hexadecimal {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/ddma_mod/temp_num_flits_in}}\n"
        ss += f"add wave -noupdate -group {x}{y}_ddma_state {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/ddma_mod/i_flip_counter}}\n"
        ss += f"add wave -noupdate -group {x}{y}_ddma_state {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/ddma_mod/i_token}}\n"
        ss += f"add wave -noupdate -group {x}{y}_ddma_state {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/ddma_mod/sstate}}\n"
        ss += f"add wave -noupdate -group {x}{y}_ddma_state {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/ddma_mod/rstate}}\n"

        ss += f"add wave -noupdate -group {x}{y}_mem_ddma {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/mem_if_dma/MEMORY_BUS_WIDTH}}\n"
        ss += f"add wave -noupdate -group {x}{y}_mem_ddma {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/mem_if_dma/data_in}}\n"
        ss += f"add wave -noupdate -group {x}{y}_mem_ddma {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/mem_if_dma/addr_in}}\n"
        ss += f"add wave -noupdate -group {x}{y}_mem_ddma {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/mem_if_dma/data_out}}\n"
        ss += f"add wave -noupdate -group {x}{y}_mem_ddma {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/mem_if_dma/enable_in}}\n"
        ss += f"add wave -noupdate -group {x}{y}_mem_ddma {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/mem_if_dma/wb_in}}\n"

        ss += f"add wave -noupdate -group {x}{y}_router -color Magenta {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/router_mod/router_mod/SwitchControl/ES}}\n"
        ss += f"add wave -noupdate -group {x}{y}_router {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/router_mod/router_mod/FLocal/EA}}\n"
        ss += f"add wave -noupdate -group {x}{y}_router {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/router_mod/router_mod/FLocal/counter_flit}}\n"
        ss += f"add wave -noupdate -group {x}{y}_router {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/router_mod/router_mod/rx}}\n"
        ss += f"add wave -noupdate -group {x}{y}_router -childformat {{{{{{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/router_mod/router_mod/data_in(4)}} -radix hexadecimal}}}} -subitemconfig {{{{/{noc_top_mod_name}/pe_x[0]/pe_y[0]/pe_mod/router_mod/router_mod/data_in(4)}} {{-height 17 -radix hexadecimal}}}} {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/router_mod/router_mod/data_in}}\n"
        ss += f"add wave -noupdate -group {x}{y}_router {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/router_mod/router_mod/credit_o}}\n"
        ss += f"add wave -noupdate -group {x}{y}_router {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/router_mod/router_mod/tx}}\n"
        ss += f"add wave -noupdate -group {x}{y}_router {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/router_mod/router_mod/data_out}}\n"
        ss += f"add wave -noupdate -group {x}{y}_router {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/router_mod/router_mod/credit_i}}\n"

        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/stall_i}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/addr_o}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/data_i}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/data_o}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/data_w_o}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/data_mode_o}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/extio_in}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/extio_out}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/stall_cpu}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/mwait_cpu}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/irq_cpu}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/irq_ack_cpu}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/exception_cpu}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/data_b_cpu}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/data_h_cpu}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/data_access_cpu}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/irq_vector_cpu}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/inst_addr_cpu}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/inst_in_cpu}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/data_addr_cpu}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/data_in_cpu}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/data_out_cpu}}\n"
        ss += f"add wave -noupdate -group {x}{y}_cpu {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/cpu_mod/processor/data_w_cpu}}\n"

        ss += f"add wave -noupdate -group {x}{y}_tcd {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/tcd_mod/timer}}\n"
        ss += f"add wave -noupdate -group {x}{y}_tcd {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/tcd_mod/timer_unlock}}\n"
        ss += f"add wave -noupdate -group {x}{y}_tcd {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/tcd_mod/HYPERPERIOD}}\n"
        ss += f"add wave -noupdate -group {x}{y}_tcd {{/{noc_top_mod_name}/pe_x[{x}]/pe_y[{y}]/pe_mod/tcd_mod/tcd_state}}\n"

    ss += "TreeUpdate [SetDefaultTree]\n"
    ss += "WaveRestoreCursors {{End Test 1} {1237119267 ps} 0 Cyan Cyan} {Trace {2308654954 ps} 0}\n"
    ss += "quietly wave cursor active 1\n"

    ss += "configure wave -namecolwidth 257\n"
    ss += "configure wave -valuecolwidth 111\n"
    ss += "configure wave -justifyvalue left\n"
    ss += "configure wave -signalnamewidth 3\n"
    ss += "configure wave -snapdistance 10\n"
    ss += "configure wave -datasetprefix 0\n"
    ss += "configure wave -rowmargin 4\n"
    ss += "configure wave -childrowmargin 2\n"
    ss += "configure wave -gridoffset 0\n"
    ss += "configure wave -gridperiod 1\n"
    ss += "configure wave -griddelta 40\n"
    ss += "configure wave -timeline 0\n"
    ss += "configure wave -timelineunits ns\n"

    ss += "update\n"
    ss += "WaveRestoreZoom {1189093392 ps} {1256113423 ps}"

    filename = expDir + "/mockup.wave.do"
    file = open(filename, "w")
    file.write(ss)
    file.close()


def exportPackets(expDir, lws, prob, lwf):
    packets = []
    base_addr = "'h0"
    # ddma_addr = "'h12345"

    STARTING_DELAY = 100

    # delete all meta files
    meta_files = glob.glob(expDir + "/meta_*")

    for file in meta_files:
        os.unlink(file)
        warn("Removing outdated file `" + file + "`")

    # for all links, get packets whose first output link if L-*
    for link in range(0, len(lws)):
        source, target, data = prob["links"][link]  # link data

        if source == "L":  # only links from output ports
            for p in range(0, len(lws[0])):
                if (
                    lws[link][p] is not None
                ):  # packet whose the output port is in the path
                    # print(prob['packets'][p])
                    #   name, flow, source (task name), target (task name),
                    #   min_start, abs_deadline, datasize, path, net_time
                    packets.append(
                        {
                            "name": prob["packets"][p]["name"],
                            "source_node": target,  # which is actually the source
                            "target_node": prob["packets"][p]["path"][-1]["edge"][
                                "source"
                            ][
                                "node"
                            ],  # destination
                            "source_xy": prob["packets"][p]["path"][0]["edge"][
                                "target"
                            ][
                                "data"
                            ],  # source
                            "target_xy": prob["packets"][p]["path"][-1]["edge"][
                                "source"
                            ][
                                "data"
                            ],  # destination
                            "data_size": prob["packets"][p][
                                "datasize"
                            ],  # number of bytes
                            "release_time": lws[link][p],  # computed release time
                        }
                    )

    def index(arr):
        return arr["source_node"]

    # sort array by link name
    packets.sort(key=index)

    for p in packets:
        debug(p)

    # sorting criterion
    def reltime(p):
        return p["release_time"]

    filename = expDir + "/mockup.sv"
    file = open(filename, "w+")

    file.write("`timescale 1ns/10ps\n\n")

    file.write("module ddma_driver_tb #(MEMORY_BUS_WIDTH, FLIT_WIDTH, ADDRESS)(\n")
    file.write("  input logic clock,\n")
    file.write("  input logic reset,\n")
    file.write("  interface_memory.DUT mem_if,\n")
    file.write("  interface_ddma.TCD ddma_if\n")
    file.write(");\n\n\n")

    file.write("integer counter = 0;\n")
    file.write("always @(posedge clock) begin\n")
    file.write("  counter <= counter + 1;\n")
    file.write("end\n\n\n")

    file.write("initial begin\n\n")
    file.write("  // delay to handle initialization offset\n")
    # file.write('  #{0}\n\n'.format(STARTING_DELAY))
    file.write("  mem_if.enable_in <= 1;\n")
    file.write("  ddma_if.addr_in <= 0;\n")
    file.write("  ddma_if.nbytes_in <= 0;\n")
    file.write("  ddma_if.cmd_in <= 0;\n")

    current_source = None
    packets_to_process = []

    # file.write("  if ")

    for p in packets:
        # make sure that first node won't be skipped
        if current_source is None:
            current_source = p["source_node"]

        # if the source has changed, or we reach the lst node,
        # sort the list, save file, clear the list
        if p["source_node"] != current_source or p == packets[-1]:
            # add condition to this packet to run
            file.write(
                "  // ============== PE NUM {0} ============== \n".format(
                    current_source
                )
            )

            xs = packets_to_process[0]["source_xy"]["X"]  # {'X': 0, 'Y': 1}
            ys = packets_to_process[0]["source_xy"]["Y"]

            source_xy_addr = (xs << 8) | ys

            # file.write("  if (ADDRESS == {0}) begin\n\n".format(current_source))
            file.write(" if (ADDRESS == {0}) begin\n\n".format(source_xy_addr))

            if p == packets[-1]:
                packets_to_process.append(p)

            # sort the list
            packets_to_process.sort(key=reltime)

            cycles = 0
            for i in range(0, len(packets_to_process)):
                e = packets_to_process[i]

                file.write("    // pkt name:     {0}\n".format(str(e["name"])))
                file.write("    // source_node:  {0}\n".format(str(e["source_node"])))
                file.write("    // target_node:  {0}\n".format(str(e["target_node"])))
                file.write("    // source_xy:    {0}\n".format(str(e["source_xy"])))
                file.write("    // target_xy:    {0}\n".format(str(e["target_xy"])))
                file.write("    // data_size:    {0}\n".format(str(e["data_size"])))
                file.write("    // release_time: {0}\n".format(str(e["release_time"])))

                # write header flit
                file.write("    mem_if.wb_in <= 1;\n")

                file.write(
                    (
                        "    mem_if.data_in <= "
                        + " ((({xs} << (FLIT_WIDTH / 4)) | {ys}) << FLIT_WIDTH / 2) |"
                        + " ((({x} << (FLIT_WIDTH / 4)) | {y}));\n"
                    ).format(x=e["target_xy"]["X"], y=e["target_xy"]["Y"], xs=xs, ys=ys)
                )

                file.write("    mem_if.addr_in <= {0};\n".format(base_addr))
                file.write("    #1;\n\n")
                cycles += 1

                num_flits: int = int(e["data_size"] / 4 + 1)

                # write size flit
                file.write("    mem_if.wb_in <= 1;\n")
                file.write(
                    "    mem_if.data_in <= {0};  // {1} bytes, size flit\n".format(
                        str(num_flits), str(int(e["data_size"]))
                    )
                )
                file.write("    mem_if.addr_in <= {0} + 'h1;\n".format(base_addr))
                file.write("    #1;\n\n")
                cycles += 1

                file.write("    mem_if.wb_in <= 0;  // lock memory write\n\n\n")
                # file.write('    mem_if.data_in = \'z;\n')
                # file.write('    mem_if.addr_in = \'z;\n')

                # wait the difference between the current
                # cycle count and the target release time
                file.write(
                    "    #{0}; // skipt to {1}\n".format(
                        str((e["release_time"] + STARTING_DELAY) - cycles),
                        str(e["release_time"]),
                    )
                )

                cycles = e["release_time"] + STARTING_DELAY

                # configure ddma
                file.write("    ddma_if.addr_in <= 'h0;\n")

                # +2 header overhead
                file.write("    ddma_if.nbytes_in <= {0};\n".format(num_flits + 2))
                file.write("    ddma_if.cmd_in <= 1;\n")
                file.write("    #1;\n\n")

                file.write("    ddma_if.addr_in <= 0;\n")
                file.write("    ddma_if.nbytes_in <= 0;\n")
                file.write("    ddma_if.cmd_in <= 0; \n")
                # file.write('    #1;\n\n')

                cycles += 1

                file.write("    #10; \n")
                cycles += 10

                # !! must acknowledge ddma protocol here
                # lock memory access
                # configure current packet
                # ddma_addr

            file.write("\n end else \n\n")  # close if for this packets

            mfile_name = expDir + "/meta_" + current_source + ".txt"
            filemeta = open(mfile_name, "w")
            for pmeta in packets_to_process:
                filemeta.write(pmeta["name"] + ": " + str(pmeta) + "\n")

            info("Generating `" + mfile_name + "`")
            filemeta.close()

            # clear the list
            packets_to_process = []

            # update current source node
            current_source = p["source_node"]

            # otherwise, append current packet to the source node list
            # else:

        packets_to_process.append(p)

    file.write("  begin\n")
    file.write("    mem_if.wb_in = 0;\n")
    file.write("    mem_if.data_in = 0;\n")
    file.write("    mem_if.addr_in = 0;\n")
    file.write("    mem_if.wb_in = 0;\n")

    file.write("    ddma_if.addr_in = 0;\n")
    file.write("    ddma_if.nbytes_in = 0;\n")
    file.write("    ddma_if.cmd_in = 0;\n")
    file.write("  end\n")

    file.write("\n\nend\n\n")
    file.write("endmodule\n\n")

    file.close()
