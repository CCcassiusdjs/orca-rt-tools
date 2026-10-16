interface interface_core_rv32e #(parameter MEMORY_BUS_WIDTH = 32)
(input clock, input reset);

  logic stall_in;

  logic[MEMORY_BUS_WIDTH-1:0] addr_out;
  logic[MEMORY_BUS_WIDTH-1:0] data_in; 
  logic[MEMORY_BUS_WIDTH-1:0] data_out;
  logic[3:0] wb_out;

  logic[2:0] data_mode_out;

  logic[7:0] extio_in;
  logic[7:0] extio_out;

  modport CPU (
    input clock, reset, stall_in, data_in, extio_in,
    output addr_out, data_out, wb_out, data_mode_out, extio_out
  );

  modport DUT (
    input clock, reset, addr_out, data_out, wb_out, data_mode_out, extio_out,
    output stall_in, data_in, extio_in
  );

endinterface: interface_core_rv32e
