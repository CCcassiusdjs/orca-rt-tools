interface interface_router_port #(parameter FLIT_WIDTH = 32)
(input clock, input reset);

  logic clock_tx;
  logic tx;
  logic credit_i;
  logic[FLIT_WIDTH -1 :0] data_o;

  logic clock_rx;
  logic rx;
  logic credit_o;
  logic[FLIT_WIDTH -1 :0] data_i;
  
  modport ROUTER (
    input clock, reset, clock_rx, rx, data_i, credit_i, 
    output clock_tx, tx, credit_o, data_o);

  modport DDMA (
    input clock, reset, clock_tx, tx, credit_o, data_o, 
    output clock_rx, rx, data_i, credit_i);

endinterface: interface_router_port