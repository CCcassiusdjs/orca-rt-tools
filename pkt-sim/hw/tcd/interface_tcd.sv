interface interface_tcd #(parameter MEMORY_BUS_WIDTH = 32)
(input clock, input reset);
  
  // from the pe
  logic input_in;
  logic[MEMORY_BUS_WIDTH-1:0] data_in;
  logic[MEMORY_BUS_WIDTH-1:0] status_out;

  modport TCD (
    input clock, reset, data_in, input_in, 
    output status_out);

  modport MMIO (
    input clock, reset, status_out,
    output data_in, input_in);

endinterface: interface_tcd