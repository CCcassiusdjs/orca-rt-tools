if {[file isdirectory work]} { vdel -all -lib work }

vlib work
vmap work work

# PACKAGES
vlog -mixedsvvh -sv -work work orca_pkg.sv

# CPU SOURCE
vlog -mixedsvvh -sv -work work ../hw/cpu/core_rv32e.sv
vlog -mixedsvvh -sv -work work ../hw/cpu/interface_core_rv32e.sv
vcom -mixedsvvh -work work -93 -explicit ../hw/cpu/core_rv32e/bshifter.vhd
vcom -mixedsvvh -work work -93 -explicit ../hw/cpu/core_rv32e/alu.vhd
vcom -mixedsvvh -work work -93 -explicit ../hw/cpu/core_rv32e/control.vhd
vcom -mixedsvvh -work work -93 -explicit ../hw/cpu/core_rv32e/int_control.vhd
vcom -mixedsvvh -work work -93 -explicit ../hw/cpu/core_rv32e/reg_bank.vhd
vcom -mixedsvvh -work work -93 -explicit ../hw/cpu/core_rv32e/datapath.vhd
vcom -mixedsvvh -work work -93 -explicit ../hw/cpu/core_rv32e/cpu.vhd

# TCD SOURCE
vlog -mixedsvvh -sv -work work ../hw/tcd/interface_tcd.sv
vlog -mixedsvvh -sv -work work ../hw/tcd/tcd.sv

# DMA SOURCE
vlog -mixedsvvh -sv -work work ../hw/ddma/interface_ddma.sv
vlog -mixedsvvh -sv -work work ../hw/ddma/ddma.sv
vlog -mixedsvvh -sv -work work ../hw/ddma/interface_router_port.sv

# MEMORY CORE SOURCE
vlog -mixedsvvh -sv -work work ../hw/memory/interface_memory.sv
vlog -mixedsvvh -sv -work work ../hw/memory/single_port_ram.sv
vlog -mixedsvvh -sv -work work ../hw/memory/dual_port_ram.sv

# NOC
vlog -mixedsvvh -sv -work work ../hw/router/interface_router.sv
vlog -mixedsvvh -sv -work work ../hw/router/router.sv
vcom -mixedsvvh -work work -93 -explicit ../hw/router/hermes/Hermes_package.vhd
vcom -mixedsvvh -work work -93 -explicit ../hw/router/hermes/Hermes_buffer.vhd
vcom -mixedsvvh -work work -93 -explicit ../hw/router/hermes/Hermes_switchcontrol.vhd
vcom -mixedsvvh -work work -93 -explicit ../hw/router/hermes/Hermes_crossbar.vhd
vcom -mixedsvvh -work work -93 -explicit ../hw/router/hermes/RouterCC.vhd

# PERIPHERALS
vcom -mixedsvvh -work work -93 -explicit ../hw/peripherals/peripherals_minimal.vhd
vlog -mixedsvvh -sv -work work ../hw/peripherals/interface_peripherals.sv
vlog -mixedsvvh -sv -work work ../hw/peripherals/peripherals.sv

# PE MOCK
vlog -mixedsvvh -sv -work work ../hw/interface_pe.sv

# TB MODS
vlog -mixedsvvh -sv -work work ./manycore_pe.sv
vlog -mixedsvvh -sv -work work ./manycore_top.sv

# ~54s   #vsim -voptargs=+acc=lprn work.manycore_top
# ~50s   #vsim -t ps work.manycore_top
# ~58s   #vsim -voptargs=+acc=lprn -t ps -debugDB work.manycore_top -wlf vsim.wlf
# ~48s   #vsim -t ns work.manycore_top

# vsim -t ns work.manycore_top
vsim work.manycore_top

# do modelsim config. override
quietly set StdArithNoWarnings 1
quietly set StdVitalGlitchNoWarnings 1

# commands from modelsim.ini 
#quietly set UnbufferedOutput 1
#quietly set SVAPrintOnlyUserMessage 1

# do ../packets/mockup.wave.do

run 1000ms
#quit


