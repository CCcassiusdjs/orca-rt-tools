interface interface_pe #(parameter MEMORY_BUS_WIDTH = 32, FLIT_WIDTH =32 )
(input clock, input reset);
  
  logic[3:0] clock_tx;   // output to router (router in)
  logic[3:0] tx;
  logic[3:0] credit_i;
  logic[3:0][FLIT_WIDTH-1:0] data_o;

  logic[3:0] clock_rx; // input from router (router out)
  logic[3:0] rx;
  logic[3:0] credit_o;
  logic[3:0][FLIT_WIDTH-1:0] data_i;

  modport PE (
    input clock, reset, clock_rx, rx, credit_i, data_i,
    output clock_tx, tx, credit_o, data_o);

  modport MESH (
    input clock, reset, clock_tx, tx, credit_o, data_o,
    output clock_rx, rx, credit_i, data_i);

endinterface: interface_pe