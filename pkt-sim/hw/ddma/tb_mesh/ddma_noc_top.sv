`timescale 1ns/10ps

module ddma_noc_top #(parameter 
  FLIT_WIDTH = 32,        // 32-bit flit width
  MEMORY_BUS_WIDTH = 32,  // memory data bus width
  MEMORY_SIZE = 'h8000,     // total memory size = 32 bits * 1024
  MEMORY_BASE = 0,        // starting address
  NOC_DIM_X = 4,
  NOC_DIM_Y = 4,
  INTERLEAVING_GRAIN = 3  
)();

  // router ports enumeration cannot be imported from Hermes definitions
  typedef enum {EAST = 0, WEST = 1, NORTH = 2, SOUTH = 3, LOCAL = 4} e_port;

  bit clock = 0;
  bit reset = 1; 

  // clock generator
  always #0.5 clock = ~clock;

  // reset goes down after 2nd cycle
  always #2 reset = 0; 

  // generate NOC_DIM_X * NOC_DIM_Y pe nodes
  genvar i, j;
  generate
    for (i = 0; i < NOC_DIM_X; i = i + 1) begin : pe_x
      for (j = 0; j < NOC_DIM_Y; j = j + 1) begin : pe_y

        // pe interface comprise all exposed wires but clock and reset
        interface_pe #(MEMORY_BUS_WIDTH, FLIT_WIDTH) pe_if(clock, reset);

        // connect an actual pe module with its interface
        // @TODO: generate pe address

        localparam ADDRESS = (i << (FLIT_WIDTH / 4)) | j;

        ddma_pe #(MEMORY_BUS_WIDTH, FLIT_WIDTH, MEMORY_SIZE, ADDRESS, INTERLEAVING_GRAIN) pe_mod(
          .clock(clock), .reset(reset),
          .pe_if(pe_if.PE)
        );
      end
    end
  endgenerate

  // connect generated routers
  generate
    for(i = 0; i < NOC_DIM_X; i++) begin : conn_x
      for(j = 0; j < NOC_DIM_Y; j++) begin : conn_y

        localparam ii = i;
        localparam jj = j;
        localparam j1 = j - 1; 
        localparam i1 = i - 1;

        // grounding west border
        if (i == 0) begin         
          assign pe_x[i].pe_y[j].pe_if.data_i[WEST][FLIT_WIDTH-1:0] = 0;
          always_comb pe_x[i].pe_y[j].pe_if.credit_i[WEST] = 1'b0;
          always_comb pe_x[i].pe_y[j].pe_if.rx[WEST] = 1'b0;
          always_comb pe_x[i].pe_y[j].pe_if.clock_rx[WEST] = 1'b0;

          $info("[", i, ",", j, "][WEST] => grounded");
          
        end else begin

          // connect to neighbor routers (X-axis)
          always_comb pe_x[i].pe_y[j].pe_if.data_i[WEST][FLIT_WIDTH-1:0] = pe_x[i-1].pe_y[j].pe_if.data_o[EAST][FLIT_WIDTH-1:0];
          always_comb pe_x[i].pe_y[j].pe_if.credit_i[WEST] = pe_x[i-1].pe_y[j].pe_if.credit_o[EAST];
          always_comb pe_x[i].pe_y[j].pe_if.rx[WEST] = pe_x[i-1].pe_y[j].pe_if.tx[EAST];
          always_comb pe_x[i].pe_y[j].pe_if.clock_rx[WEST] = pe_x[i-1].pe_y[j].pe_if.clock_tx[EAST];

          always_comb pe_x[i-1].pe_y[j].pe_if.data_i[EAST][FLIT_WIDTH-1:0] = pe_x[i].pe_y[j].pe_if.data_o[WEST][FLIT_WIDTH-1:0];
          always_comb pe_x[i-1].pe_y[j].pe_if.credit_i[EAST] = pe_x[i].pe_y[j].pe_if.credit_o[WEST];
          always_comb pe_x[i-1].pe_y[j].pe_if.rx[EAST] = pe_x[i].pe_y[j].pe_if.tx[WEST];
          always_comb pe_x[i-1].pe_y[j].pe_if.clock_rx[EAST] = pe_x[i].pe_y[j].pe_if.clock_tx[WEST];

          $info("[", i, ",", j, "][WEST] => connected to [", (i-1), ",", j, "][EAST]");

        end

        // grounding east border
        if (i == NOC_DIM_X-1) begin
          always_comb pe_x[i].pe_y[j].pe_if.data_i[EAST][FLIT_WIDTH-1:0] = 0;
          always_comb pe_x[i].pe_y[j].pe_if.credit_i[EAST] = 1'b0;
          always_comb pe_x[i].pe_y[j].pe_if.rx[EAST] = 1'b0;
          always_comb pe_x[i].pe_y[j].pe_if.clock_rx[EAST] = 1'b0;

          $info("[", i, ",", j, "][EAST] => grounded");

        end

        if (j == 0) begin
          // grounding south border
          always_comb pe_x[i].pe_y[j].pe_if.data_i[SOUTH][FLIT_WIDTH-1:0] = 0;
          always_comb pe_x[i].pe_y[j].pe_if.credit_i[SOUTH] = 1'b0;
          always_comb pe_x[i].pe_y[j].pe_if.rx[SOUTH] = 1'b0;
          always_comb pe_x[i].pe_y[j].pe_if.clock_rx[SOUTH] = 1'b0;

          $info("[", i, ",", j, "][SOUTH] => grounded");

        end else begin

          $info("[", i, ",", j, "][SOUTH] => connected to [", i, ",", (j-1), "][NORTH]");

          // connect to neighbor routers (Y-axis)
          always_comb pe_x[i].pe_y[j].pe_if.data_i[SOUTH][FLIT_WIDTH-1:0] = pe_x[i].pe_y[j-1].pe_if.data_o[NORTH][FLIT_WIDTH-1:0];
          always_comb pe_x[i].pe_y[j].pe_if.credit_i[SOUTH] = pe_x[i].pe_y[j-1].pe_if.credit_o[NORTH];
          always_comb pe_x[i].pe_y[j].pe_if.rx[SOUTH] = pe_x[i].pe_y[j-1].pe_if.tx[NORTH];
          always_comb pe_x[i].pe_y[j].pe_if.clock_rx[SOUTH] = pe_x[i].pe_y[j-1].pe_if.clock_tx[NORTH];

          always_comb pe_x[i].pe_y[j-1].pe_if.data_i[NORTH][FLIT_WIDTH-1:0] = pe_x[i].pe_y[j].pe_if.data_o[SOUTH][FLIT_WIDTH-1:0];
          always_comb pe_x[i].pe_y[j-1].pe_if.credit_i[NORTH] = pe_x[i].pe_y[j].pe_if.credit_o[SOUTH];
          always_comb pe_x[i].pe_y[j-1].pe_if.rx[NORTH] = pe_x[i].pe_y[j].pe_if.tx[SOUTH];
          always_comb pe_x[i].pe_y[j-1].pe_if.clock_rx[NORTH] = pe_x[i].pe_y[j].pe_if.clock_tx[SOUTH];

        end 

        if(j == NOC_DIM_Y-1) begin

          $info("[", i, ",", j, "][NORTH] => grounded");

          // grounding north border
          always_comb pe_x[i].pe_y[j].pe_if.data_i[NORTH][FLIT_WIDTH-1:0] = 0;
          always_comb pe_x[i].pe_y[j].pe_if.credit_i[NORTH] = 1'b0;
          always_comb pe_x[i].pe_y[j].pe_if.rx[NORTH] = 1'b0;
          always_comb pe_x[i].pe_y[j].pe_if.clock_rx[NORTH] = 1'b0;
        end
      end
    end
  endgenerate
        
endmodule: ddma_noc_top