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

# NOC
vlog -mixedsvvh -sv -work work ../../router/interface_router.sv
vlog -mixedsvvh -sv -work work ../../router/router.sv
vcom -mixedsvvh -work work -93 -explicit ../../router/hermes/Hermes_package.vhd
vcom -mixedsvvh -work work -93 -explicit ../../router/hermes/Hermes_buffer.vhd
vcom -mixedsvvh -work work -93 -explicit ../../router/hermes/Hermes_switchcontrol.vhd
vcom -mixedsvvh -work work -93 -explicit ../../router/hermes/Hermes_crossbar.vhd
vcom -mixedsvvh -work work -93 -explicit ../../router/hermes/RouterCC.vhd


# PE MOCK
vlog -mixedsvvh -sv -work work ../../interface_pe.sv

# TB DRIVERS
vlog -mixedsvvh -sv -work work ../../../packets/mockup.sv

# TB MODS
vlog -mixedsvvh -sv -work work ./ddma_pe.sv
vlog -mixedsvvh -sv -work work ./ddma_noc_top.sv

vsim -voptargs=+acc=lprn -t ps -debugDB work.ddma_noc_top
#vsim -t ps -debugDB work.tb

quietly set StdArithNoWarnings 1
quietly set StdVitalGlitchNoWarnings 1

#do wave.do
#view -new schematic
do ../../../packets/mockup.wave.do

run 0 ns

quietly set StdArithNoWarnings 1
quietly set StdVitalGlitchNoWarnings 1

#run 2500 us
do ../../../packets/mockup.run.do


