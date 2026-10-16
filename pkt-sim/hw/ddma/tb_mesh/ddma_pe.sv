module ddma_pe #(parameter
  MEMORY_BUS_WIDTH, 
  FLIT_WIDTH,
  MEMORY_SIZE,
  ADDRESS = 0,
  INTERLEAVING_GRAIN
)(
  input logic clock,
  input logic reset,
  interface_pe.PE pe_if
);

  interface_router #(FLIT_WIDTH) router_if(clock, reset); // router and pe

  // interface to actual modules
  interface_router_port #(FLIT_WIDTH) router_port_if(clock, reset); // router and ddma
  interface_memory #(MEMORY_BUS_WIDTH) mem_if_dma(clock, reset); // mem and ddma
  interface_memory #(MEMORY_BUS_WIDTH) mem_if_mmio(clock, reset); // mem and mmio
  interface_ddma   #(MEMORY_BUS_WIDTH, FLIT_WIDTH, INTERLEAVING_GRAIN, ADDRESS) ddma_if(clock, reset); //tcd and ddma

  logic cpu_irq;

  // create new scratchpad 
  dual_port_ram #(MEMORY_BUS_WIDTH, MEMORY_SIZE) memory_mod(
    .clock(clock), .reset(reset),
    .mem_if_a(mem_if_dma.MEM),
    .mem_if_b(mem_if_mmio.MEM)
  );

  // creates new ddma module
  ddma #(MEMORY_BUS_WIDTH, FLIT_WIDTH, INTERLEAVING_GRAIN, ADDRESS) ddma_mod(
    .clock(clock), .reset(reset), 
    .router_if(router_port_if.DDMA),
    .mem_if(mem_if_dma.DUT),
    .ddma_if(ddma_if.DDMA),
    .irq(cpu_irq)
  );

  // !+++++ PENUM
  ddma_driver_tb #(MEMORY_BUS_WIDTH, FLIT_WIDTH, ADDRESS) ddma_tb_mod(
    .clock(clock), .reset(reset),
    .mem_if(mem_if_mmio),
    .ddma_if(ddma_if)
  );

  // new router
  router #(ADDRESS) router_mod (
    .clock(clock), .reset(reset),
    .router_if(router_if.ROUTER)
  );

  // connect router interface to pe interface (only SNWE ports)
  always_comb begin
    pe_if.clock_tx[3:0] = router_if.clock_tx[3:0];
    pe_if.tx[3:0] = router_if.tx[3:0];
    pe_if.data_o[3:0] = router_if.data_o[3:0];
    pe_if.credit_o[3:0] = router_if.credit_o[3:0];

    router_if.clock_rx[3:0] = pe_if.clock_rx[3:0];
    router_if.rx[3:0] = pe_if.rx[3:0];
    router_if.data_i[3:0] = pe_if.data_i[3:0];
    router_if.credit_i[3:0] = pe_if.credit_i[3:0];
  end

  // connect router local port to the ddma
  always_comb begin
    router_port_if.clock_tx <= router_if.clock_tx[4];
    router_port_if.tx <= router_if.tx[4];
    router_port_if.data_o <= router_if.data_o[4];
    router_port_if.credit_o <= router_if.credit_o[4];

    router_if.clock_rx[4] <= router_port_if.clock_rx;
    router_if.rx[4] <= router_port_if.rx;
    router_if.data_i[4] <= router_port_if.data_i;
    router_if.credit_i[4] <= router_port_if.credit_i;
  end


endmodule: ddma_pe

