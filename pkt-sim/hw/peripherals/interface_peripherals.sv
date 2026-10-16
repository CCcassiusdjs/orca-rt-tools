interface interface_peripherals #(parameter MEMORY_BUS_WIDTH = 32)
(input clock, input reset);

	logic[MEMORY_BUS_WIDTH-1:0]	addr_in;  // addr_i
	logic[MEMORY_BUS_WIDTH-1:0] data_in;  // data_i
	logic[MEMORY_BUS_WIDTH-1:0] data_out; // data_o
	logic	sel_in; // sel_i
	logic wr_in;  // wr_i
	logic irq;    //irq_o
	logic[7:0] gpioa_in;  //in 
	logic[7:0] gpioa_out; //out 
	logic[7:0] gpioa_ddr; //out

  modport PERIPHERALS (
    input clock, reset, data_in, addr_in, sel_in, wr_in, gpioa_in,
    output data_out, irq, gpioa_out, gpioa_ddr);

  modport TOP (
    input clock, reset, data_out, irq, gpioa_out, gpioa_ddr,
    output data_in, addr_in, sel_in, wr_in, gpioa_in);

endinterface: interface_peripherals