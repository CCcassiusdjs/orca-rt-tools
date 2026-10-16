interface interface_memory #(parameter MEMORY_BUS_WIDTH = 32)
(input clock, input reset);
  logic[MEMORY_BUS_WIDTH-1:0] data_in; // mem. interface
  logic[MEMORY_BUS_WIDTH-1:0] addr_in;
  logic[MEMORY_BUS_WIDTH-1:0] data_out;
  logic[3:0] wb_in;

  modport MEM (
    input data_in, addr_in, wb_in, clock, reset,
    output data_out);

  modport DUT (
    output data_in, addr_in, wb_in, 
    input data_out, clock, reset);

endinterface: interface_memory
