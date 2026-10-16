onerror {resume}
quietly WaveActivateNextPane {} 0
add wave -noupdate /ddma_top/clock
add wave -noupdate /ddma_top/reset
add wave -noupdate -expand -group ddma_if /ddma_top/ddma_if/addr_in
add wave -noupdate -expand -group ddma_if /ddma_top/ddma_if/nbytes_in
add wave -noupdate -expand -group ddma_if /ddma_top/ddma_if/cmd_in
add wave -noupdate -expand -group ddma_if /ddma_top/ddma_if/status_out
add wave -noupdate -expand -group ddma_if /ddma_top/ddma_if/irq_out
add wave -noupdate -expand -group router_port_if /ddma_top/router_port_if/tx
add wave -noupdate -expand -group router_port_if /ddma_top/router_port_if/credit_i
add wave -noupdate -expand -group router_port_if -color Yellow /ddma_top/router_port_if/data_o
add wave -noupdate -expand -group router_port_if /ddma_top/router_port_if/rx
add wave -noupdate -expand -group router_port_if /ddma_top/router_port_if/credit_o
add wave -noupdate -expand -group router_port_if -radix decimal /ddma_top/router_port_if/data_i
add wave -noupdate -expand -group ddma_internals /ddma_top/ddma_mod/irq
add wave -noupdate -expand -group ddma_internals /ddma_top/ddma_mod/has_data_to_send
add wave -noupdate -expand -group ddma_internals /ddma_top/ddma_mod/has_data_to_recv
add wave -noupdate -expand -group ddma_internals /ddma_top/ddma_mod/RECV_BUFFER_SIZE
add wave -noupdate -expand -group ddma_internals /ddma_top/ddma_mod/memory_pointer_recv
add wave -noupdate -expand -group ddma_internals /ddma_top/ddma_mod/i_token
add wave -noupdate -expand -group ddma_internals /ddma_top/ddma_mod/i_flip_counter
add wave -noupdate -expand -group ddma_internals /ddma_top/ddma_mod/sstate
add wave -noupdate -expand -group ddma_internals -radix decimal -radixshowbase 1 /ddma_top/ddma_mod/temp_addr_in
add wave -noupdate -expand -group ddma_internals -radix decimal /ddma_top/ddma_mod/temp_nbytes_in
add wave -noupdate -expand -group ddma_internals /ddma_top/ddma_mod/rstate
add wave -noupdate -expand -group ddma_internals -radix decimal -radixshowbase 0 /ddma_top/ddma_mod/packet_size
add wave -noupdate -expand -group ddma_internals -radix decimal -radixshowbase 0 /ddma_top/ddma_mod/flits_to_recv
add wave -noupdate -expand -group mem_ddma_if /ddma_top/mem_if_dma/data_in
add wave -noupdate -expand -group mem_ddma_if -radix decimal /ddma_top/mem_if_dma/addr_in
add wave -noupdate -expand -group mem_ddma_if -radix decimal /ddma_top/mem_if_dma/data_out
add wave -noupdate -expand -group mem_ddma_if /ddma_top/mem_if_dma/enable_in
add wave -noupdate -expand -group mem_ddma_if /ddma_top/mem_if_dma/wb_in
add wave -noupdate -group mem_UNUSED_if /ddma_top/mem_if_mmio/data_in
add wave -noupdate -group mem_UNUSED_if /ddma_top/mem_if_mmio/addr_in
add wave -noupdate -group mem_UNUSED_if /ddma_top/mem_if_mmio/data_out
add wave -noupdate -group mem_UNUSED_if /ddma_top/mem_if_mmio/enable_in
add wave -noupdate -group mem_UNUSED_if /ddma_top/mem_if_mmio/wb_in
TreeUpdate [SetDefaultTree]
WaveRestoreCursors {{End Test 1} {34821 ps} 1 Cyan Cyan} {{End Test 2} {109059 ps} 1 Cyan Cyan} {{End Test 3} {150433 ps} 1 default Cyan} {{Cursor 4} {131849 ps} 0}
quietly wave cursor active 4
configure wave -namecolwidth 257
configure wave -valuecolwidth 112
configure wave -justifyvalue left
configure wave -signalnamewidth 3
configure wave -snapdistance 10
configure wave -datasetprefix 0
configure wave -rowmargin 4
configure wave -childrowmargin 2
configure wave -gridoffset 0
configure wave -gridperiod 1
configure wave -griddelta 40
configure wave -timeline 0
configure wave -timelineunits ns
update
WaveRestoreZoom {0 ps} {210 ns}
