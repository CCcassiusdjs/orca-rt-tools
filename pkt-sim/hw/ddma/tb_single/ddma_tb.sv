`timescale 1ns/10ps

module ddma_tb #(parameter MEMORY_BUS_WIDTH, FLIT_WIDTH)(
  input logic clock,
  input logic reset,
  interface_router_port.ROUTER router_if,
  interface_memory.DUT mem_if, // mmio, grounded
  interface_ddma.TCD ddma_if
);

  integer counter = 0;
  
  always @(posedge clock) begin
    counter <= counter + 1;
  end 


  logic cpu_irq;

  // ground unused memory port
  always @(posedge clock) begin
    if(~reset) begin
      mem_if.enable_in = 0;
      mem_if.wb_in = 0;
      mem_if.data_in = 0;
      mem_if.addr_in = 0;
    end 
  end 

  // drive tcd signals
  initial begin

    router_if.clock_tx = clock;
    router_if.data_o = counter;

    // ================================== [TEST 1]
    //      free sending, no contention
    // ===========================================

    router_if.credit_o = 1;      // enable sending (router)
    router_if.tx = 0;            // disable receiving

    #1;
    ddma_if.cmd_in = 0;
    #2;
    ddma_if.addr_in = 55;        // configure mem copy addr
    #2;
    ddma_if.nbytes_in = 9;       // configure num of bytes
    #2;
    ddma_if.cmd_in = 1;          // start copy
    #6;
    ddma_if.cmd_in = 0;          // acknowledgement

    #2;
    ddma_if.addr_in = 15;        // configure mem copy addr
    #2;
    ddma_if.nbytes_in = 19;       // configure num of bytes
    #2;
    ddma_if.cmd_in = 1;          // start copy
    #8;
    ddma_if.cmd_in = 0;          // acknowledgement

    #20;
    // ================================== [TEST 2]
    //    free sending, simulated contention
    // ===========================================
    router_if.credit_o = 1;      // enable sending (router)
    router_if.tx = 0;            // disable receiving

    #2;
    ddma_if.addr_in = 15;        // configure mem copy addr
    #2;
    ddma_if.nbytes_in = 60;       // configure num of bytes
    #2;
    ddma_if.cmd_in = 1;          // start copy
    #6;
    router_if.credit_o = 0;      // 5 cycles contention
    #10;
    router_if.credit_o = 1;      
    #10;
    router_if.credit_o = 0;      // 6 cycles contention
    #12;
    router_if.credit_o = 1;      
    #10;
    ddma_if.cmd_in = 0;          // acknowledgement

    #20;
    // ================================== [TEST 3]
    //    free recving, no contention
    // ===========================================
    // router_if.credit_o = 0;      // disable sending 
    router_if.tx = 1;            // enable receiving

    router_if.data_o = 0;  //addr
    #2;  //recv takes 1 cycle to acquire token
    router_if.data_o = 9;
    #2 router_if.data_o = 8;
    #2 router_if.data_o = 7;
    #2 router_if.data_o = 6;
    #2 router_if.data_o = 5;
    #2 router_if.data_o = 4;
    #2 router_if.data_o = 3;
    #2 router_if.data_o = 2;
    #2 router_if.data_o = 1;
    #2;
    router_if.data_o = 0;
    router_if.tx = 0;
    router_if.data_o = 0;

    #20;
    // ================================== [TEST 4]
    //    free recving, 2-cycle contention
    // ===========================================
    router_if.credit_o = 0;      // disable sending 
    router_if.data_o = 5;
    router_if.tx = 1;            // enable receiving

    #6 router_if.data_o = 5;  // header
    #2 router_if.data_o = 1;  // size
    #2 router_if.data_o = 2;  //payload
    
    router_if.tx = 0;
    #4 router_if.tx = 1;  // 2 cycles contention

    #2 router_if.data_o = 3;
    #2 router_if.data_o = 4;
    #2 router_if.data_o = 5;
    #2;
    router_if.tx = 0;
    router_if.data_o = 0;


  end

endmodule: ddma_tb

