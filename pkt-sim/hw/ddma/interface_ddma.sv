interface interface_ddma #(parameter 
  MEMORY_BUS_WIDTH = 32, 
  FLIT_WIDTH = 32, 
  INTERLEAVING_GRAIN = 10, 
  ADDRESS = 0
)(input clock, input reset);
  
  //to dma
  logic[MEMORY_BUS_WIDTH-1:0] send_addr_in;
  logic[MEMORY_BUS_WIDTH-1:0] send_size_in;
  logic[MEMORY_BUS_WIDTH-1:0] send_dest_in;
  logic send_cmd_in;

  //from dma
  logic[MEMORY_BUS_WIDTH-1:0] recv_addr_in;
  logic[MEMORY_BUS_WIDTH-1:0] recv_addr_out;
  logic[MEMORY_BUS_WIDTH-1:0] recv_size_out;
  logic recv_cmd_in;

  // soft. status byte = X X XXX XXX
  logic irq_send_out;
  logic irq_recv_size_out;
  logic irq_recv_hshk_out;
  logic[7:0] state_recv_out;
  logic[7:0] state_send_out;
  

  modport DDMA (
    input clock, reset, 
          send_addr_in, send_size_in, send_cmd_in, send_dest_in,
          recv_addr_in, recv_cmd_in,
    output state_recv_out, state_send_out, recv_size_out, recv_addr_out,
           irq_recv_size_out, irq_recv_hshk_out, irq_send_out);

  modport TCD (
    output send_addr_in, send_size_in, send_cmd_in, send_dest_in,
           recv_addr_in, recv_cmd_in, recv_addr_out,
    input clock, reset, recv_size_out,
          state_recv_out, state_send_out, 
          irq_recv_size_out, irq_recv_hshk_out, irq_send_out);

endinterface: interface_ddma