if {[file isdirectory work]} { vdel -all -lib work }

vlib work
vmap work work

# DMA SOURCE
vlog -mixedsvvh -sv -work work ../ddma.sv
vlog -mixedsvvh -sv -work work ../interface_router_port.sv
vlog -mixedsvvh -sv -work work ../interface_ddma.sv

# MEMORY CORE SOURCE
vlog -mixedsvvh -sv -work work ../../memory/dual_port_ram.sv
vlog -mixedsvvh -sv -work work ../../memory/interface_memory.sv

# TB MODS
vlog -mixedsvvh -sv -work work ./ddma_top.sv
vlog -mixedsvvh -sv -work work ./ddma_tb.sv

vsim -voptargs=+acc=lprn -t ps -debugDB work.ddma_top
#vsim -t ps -debugDB work.tb

quietly set StdArithNoWarnings 1
quietly set StdVitalGlitchNoWarnings 1

do wave.do
#view -new schematic

run 0 ns

quietly set StdArithNoWarnings 0
quietly set StdVitalGlitchNoWarnings 0

run 200 ns


