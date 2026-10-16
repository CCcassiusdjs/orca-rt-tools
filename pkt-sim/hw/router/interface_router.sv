typedef logic[4:0][31:0] arrayNport_regflit; 

interface interface_router #(parameter FLIT_WIDTH = 32)
(input clock, input reset);

  logic[4:0] clock_tx;
  logic[4:0] tx;
  logic[4:0] credit_i;
  logic[4:0][FLIT_WIDTH-1:0] data_o;

  logic[4:0] clock_rx;
  logic[4:0] rx;
  logic[4:0] credit_o;
  logic[4:0][FLIT_WIDTH-1:0] data_i;
  
  modport ROUTER (
    input clock, reset, clock_rx, rx, data_i, credit_i, 
    output clock_tx, tx, credit_o, data_o);

  modport DUT (
    input clock, reset, clock_tx, tx, credit_o, data_o, 
    output clock_rx, rx, data_i, credit_i);

endinterface: interface_router