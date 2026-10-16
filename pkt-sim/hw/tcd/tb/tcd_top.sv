`timescale 1 ns / 1 ns

module ddma_top #(parameter
  MEMORY_BUS_WIDTH = 32, 
  FLIT_WIDTH = 32,
  MEMORY_SIZE = 1024
)();

  logic clock = 0;
  logic reset = 1; 

  // clock generator
  // reset goes down after 2nd cycle
  always #1 clock = ~clock;
  always #2 reset = 0;

  // interface instances 
  interface_router_port #(FLIT_WIDTH) router_port_if(clock, reset); // router and ddma
  interface_memory #(MEMORY_BUS_WIDTH) mem_if_dma(clock, reset); // mem and ddma
  interface_memory #(MEMORY_BUS_WIDTH) mem_if_mmio(clock, reset); // mem and mmio
  interface_ddma   #(MEMORY_BUS_WIDTH, FLIT_WIDTH) ddma_if(clock, reset); //tcd and ddma

  logic cpu_irq;

  // create new scratchpad 
  dual_port_ram #(MEMORY_BUS_WIDTH, MEMORY_SIZE) memory_mod(
    .clock(clock), .reset(reset),
    .mem_if_a(mem_if_dma.MEM),
    .mem_if_b(mem_if_mmio.MEM)
  );

  // creates new ddma module
  ddma #(MEMORY_BUS_WIDTH, FLIT_WIDTH, 3) ddma_mod(
    .clock(clock), .reset(reset), 
    .router_if(router_port_if.DDMA),
    .mem_if(mem_if_dma.DUT),
    .ddma_if(ddma_if.DDMA),
    .irq(cpu_irq)
  );

  ddma_tb #(MEMORY_BUS_WIDTH, FLIT_WIDTH) ddma_tb_mod(
    .clock(clock), .reset(reset),
    .router_if(router_port_if),
    .mem_if(mem_if_mmio),
    .ddma_if(ddma_if)
  );

endmodule: ddma_top

