# Diagnostic run of one PE of run MA (experiments/multiapp, make diag):
# simulate.sh runs this file in place of `run -all` (RUN_DO).
#
# Environment:
#   DIAG_DIR       output directory (required)
#   DIAG_X DIAG_Y  PE (default 0 1: PE 4, task BFE3 of CAR-V)
#   DIAG_CYCLE_FS  clock period in fs (default 2299314: 434.912 MHz,
#                  2 x CLOCK_HALF_PERIOD_FS of run MA)
#   DIAG_WINDOWS   start instants (ns) of the per-cycle traces (default
#                  "5699500 6199500": the end of iteration 5 and of
#                  iteration 6 of BFE3, 1,800 cycles each)
#   DIAG_SNAPSHOTS instants (ns) of the snapshots (default "6210000
#                  6300000": registers, memory of the PE, 400 cycles of
#                  trace)
#
# Outputs in DIAG_DIR: diag.txt (paths, then one line per cycle of the
# windows: time, PC and the signals below, and the 16 registers at each
# snapshot) and pe<x>-<y>.<t>ns.mem (memory_mod.mem of the PE, one word per
# line, hex, at each snapshot). The design stops after the last snapshot.

quietly set dir $env(DIAG_DIR)
file mkdir $dir
quietly set x 0
quietly set y 1
if {[info exists env(DIAG_X)]} { quietly set x $env(DIAG_X) }
if {[info exists env(DIAG_Y)]} { quietly set y $env(DIAG_Y) }
quietly set cycle 2299314
if {[info exists env(DIAG_CYCLE_FS)]} { quietly set cycle $env(DIAG_CYCLE_FS) }
quietly set windows {5699500 6199500}
if {[info exists env(DIAG_WINDOWS)]} { quietly set windows $env(DIAG_WINDOWS) }
quietly set snapshots {6210000 6300000}
if {[info exists env(DIAG_SNAPSHOTS)]} { quietly set snapshots $env(DIAG_SNAPSHOTS) }
quietly set window_cycles 1800
quietly set snapshot_cycles 400

quietly set f [open [file join $dir diag.txt] w]
puts $f "# diag_pe.do: PE $x-$y, cycle $cycle fs, windows $windows ns ($window_cycles cycles), snapshots $snapshots ns"

# instance path of the PE (generate blocks pe_x/pe_y of manycore_top)
quietly set pe ""
foreach cand [list "/manycore_top/pe_x\[$x\]/pe_y\[$y\]/pe_mod" "/manycore_top/pe_x($x)/pe_y($y)/pe_mod"] {
	if {![catch {examine $cand/cpu_mod/processor/core/pc}]} {
		quietly set pe $cand
		break
	}
}
if {$pe eq ""} {
	puts $f "# no PE path found; instances:"
	catch {puts $f [find instances -recursive /manycore_top/*]}
	close $f
	quit -f
}
puts $f "# pe $pe"

quietly set core $pe/cpu_mod/processor/core
quietly set ic $pe/cpu_mod/processor/int_control
# name path: datapath (PC, pipeline flags), interrupt controller, CPU bus,
# instrumentation registers of manycore_pe.sv
quietly set wanted [list \
	pc $core/pc pc_last $core/pc_last inst $core/inst_in_s \
	irq_ack $core/irq_ack_s bds $core/bds branch $core/branch_taken jump $core/jump_taken \
	mem_to_reg_r $core/mem_to_reg_r reg_to_mem_r $core/reg_to_mem_r \
	irq $ic/irq interrupt $ic/interrupt status $ic/irq_status_reg mask $ic/irq_mask_reg \
	cause $ic/irq_cause epc $ic/irq_epc_reg pulse $ic/pulse_state \
	extio_in $pe/cpu_if/extio_in addr $pe/cpu_if/addr_out wb $pe/cpu_if/wb_out data_out $pe/cpu_if/data_out \
	sched $pe/cacc_counter_2 send $pe/cacc_counter_3 recv $pe/cacc_counter_4 iter $pe/cacc_iter]
quietly set sig {}
foreach {name path} $wanted {
	if {[catch {examine -radix hex $path} msg]} {
		puts $f "# missing $name ($path): $msg"
	} else {
		lappend sig $name $path
	}
}
puts $f "# columns: time [join [dict keys $sig] { }]"

proc sample {f sig} {
	set line [now]
	foreach {name path} $sig {
		append line " $name=[examine -radix hex $path]"
	}
	puts $f $line
}

proc trace {f sig n cycle} {
	for {set i 0} {$i < $n} {incr i} {
		sample $f $sig
		run ${cycle}fs
	}
}

foreach t $windows {
	run @${t}ns
	puts $f "# window $t ns"
	trace $f $sig $window_cycles $cycle
	flush $f
}
foreach t $snapshots {
	run @${t}ns
	puts $f "# snapshot $t ns"
	if {[catch {examine -radix hex $core/register_bank/registers} regs]} {
		puts $f "# registers: $regs"
	} else {
		puts $f "registers x0..x15 = $regs"
	}
	set mem [file join $dir "pe$x-$y.${t}ns.mem"]
	if {[catch {mem save -outfile $mem -format hex -noaddress -wordsperline 1 $pe/memory_mod/mem} msg]} {
		puts $f "# mem save: $msg"
	}
	trace $f $sig $snapshot_cycles $cycle
	flush $f
}
close $f
quit -f
