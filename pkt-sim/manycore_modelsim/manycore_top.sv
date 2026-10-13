`timescale 1ns/100ps
//`timescale 10ps/10ps


module manycore_top #(parameter 
  // CLOCK_BORDER_PERIOD = 2020, // 2 => ns, 18 -> 900ps, 
  CLOCK_BORDER_PERIOD = 2,
  FLIT_WIDTH = 32,        // 32-bit flit width
  MEMORY_BUS_WIDTH = 32,  // memory data bus width
  RAM_MSIZE = 65536,      //32768, 65536   // 32k, 65k bytes
  BOOT_MSIZE = 1024,     // 2k bytes
  NOC_DIM_X = 2,
  NOC_DIM_Y = 2,
  INTERLEAVING_GRAIN = 10,  // switch input after 10 cycles
  // Release generator (manycore_pe.sv). Bit k of RELEASE_MASK enables the
  // generator of the PE with node index k = y * NOC_DIM_X + x, the index
  // of the software (device/ddma.c, _ddma_node_addr) and of the .map files.
  // The default (PE 0) is the setup of application E (weird_a.c); a run
  // sets it with vsim -g (experiments/exp23/simulate.sh).
  parameter logic [63:0] RELEASE_MASK = 64'd1
)();

  // router ports enumeration cannot be imported from Hermes definitions
  typedef enum {EAST = 0, WEST = 1, NORTH = 2, SOUTH = 3, LOCAL = 4} e_port;

  bit clock = 0;
  bit reset = 1; 

  // clock generator
  always # (CLOCK_BORDER_PERIOD / 2.0) clock = ~clock;

  // reset goes down after 2nd cycle
  always # (CLOCK_BORDER_PERIOD * 2.0) reset = 0; 

  // simulation time reporting
  always #1_000_000 $display("Elapsed %0d nanoseconds.", $realtime);

  // generate NOC_DIM_X * NOC_DIM_Y pe nodes
  genvar i, j;
  generate
    for (i = 0; i < NOC_DIM_X; i = i + 1) begin : pe_x
      for (j = 0; j < NOC_DIM_Y; j = j + 1) begin : pe_y

        // pe interface comprise all exposed wires but clock and reset
        interface_pe #(MEMORY_BUS_WIDTH, FLIT_WIDTH) pe_if(clock, reset);
        localparam X = i;
        localparam Y = j;
        localparam YDIM = NOC_DIM_Y;
        localparam XDIM = NOC_DIM_X;

        // adds noc dimension to the most significant bytes,
        // and appends router address to the lower bytes.
        // word format is (32-bit length):
        // |-----------|-----------|-----------|----------|
        // |---DIM X---|---DIM Y---|--ADDR X---|--ADDR Y--|
        // |-----------|-----------|-----------|----------|
        localparam DIM = (XDIM << 24) | (YDIM << 16);
        localparam XY = (X << 8) | Y;
        localparam ADDRESS = DIM | XY;

        manycore_pe #(MEMORY_BUS_WIDTH, FLIT_WIDTH, RAM_MSIZE, BOOT_MSIZE,
          ADDRESS, INTERLEAVING_GRAIN, NOC_DIM_X, NOC_DIM_Y,
          RELEASE_MASK
        ) pe_mod(
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
          assign pe_x[i].pe_y[j].pe_if.credit_i[WEST] = 1'b0;
          assign pe_x[i].pe_y[j].pe_if.rx[WEST] = 1'b0;
          assign pe_x[i].pe_y[j].pe_if.clock_rx[WEST] = 1'b0;
          
          $info("mesh connection (%0d, %0d) WEST => grounded", i, j);
          
        end else begin

          // connect to neighbor routers (X-axis)
          assign pe_x[i].pe_y[j].pe_if.data_i[WEST][FLIT_WIDTH-1:0] = pe_x[i-1].pe_y[j].pe_if.data_o[EAST][FLIT_WIDTH-1:0];
          assign pe_x[i].pe_y[j].pe_if.credit_i[WEST] = pe_x[i-1].pe_y[j].pe_if.credit_o[EAST];
          assign pe_x[i].pe_y[j].pe_if.rx[WEST] = pe_x[i-1].pe_y[j].pe_if.tx[EAST];
          assign pe_x[i].pe_y[j].pe_if.clock_rx[WEST] = pe_x[i-1].pe_y[j].pe_if.clock_tx[EAST];

          assign pe_x[i-1].pe_y[j].pe_if.data_i[EAST][FLIT_WIDTH-1:0] = pe_x[i].pe_y[j].pe_if.data_o[WEST][FLIT_WIDTH-1:0];
          assign pe_x[i-1].pe_y[j].pe_if.credit_i[EAST] = pe_x[i].pe_y[j].pe_if.credit_o[WEST];
          assign pe_x[i-1].pe_y[j].pe_if.rx[EAST] = pe_x[i].pe_y[j].pe_if.tx[WEST];
          assign pe_x[i-1].pe_y[j].pe_if.clock_rx[EAST] = pe_x[i].pe_y[j].pe_if.clock_tx[WEST];
          
          $info("mesh connection (%0d, %0d) WEST => (%0d, %0d) EAST", i, j, (i-1), j);

        end

        // grounding east border
        if (i == NOC_DIM_X-1) begin
          assign pe_x[i].pe_y[j].pe_if.data_i[EAST][FLIT_WIDTH-1:0] = 0;
          assign pe_x[i].pe_y[j].pe_if.credit_i[EAST] = 1'b0;
          assign pe_x[i].pe_y[j].pe_if.rx[EAST] = 1'b0;
          assign pe_x[i].pe_y[j].pe_if.clock_rx[EAST] = 1'b0;

          $info("mesh connection (%0d, %0d) EAST => grounded", i, j);

        end

        if (j == 0) begin
          // grounding south border
          assign pe_x[i].pe_y[j].pe_if.data_i[SOUTH][FLIT_WIDTH-1:0] = 0;
          assign pe_x[i].pe_y[j].pe_if.credit_i[SOUTH] = 1'b0;
          assign pe_x[i].pe_y[j].pe_if.rx[SOUTH] = 1'b0;
          assign pe_x[i].pe_y[j].pe_if.clock_rx[SOUTH] = 1'b0;

          $info("mesh connection (%0d, %0d) SOUTH => grounded", i, j);

        end else begin

          $info("mesh connection (%0d, %0d) SOUTH => (%0d, %0d) NORTH", i, j, i, (j-1));

          // connect to neighbor routers (Y-axis)
          assign pe_x[i].pe_y[j].pe_if.data_i[SOUTH][FLIT_WIDTH-1:0] = pe_x[i].pe_y[j-1].pe_if.data_o[NORTH][FLIT_WIDTH-1:0];
          assign pe_x[i].pe_y[j].pe_if.credit_i[SOUTH] = pe_x[i].pe_y[j-1].pe_if.credit_o[NORTH];
          assign pe_x[i].pe_y[j].pe_if.rx[SOUTH] = pe_x[i].pe_y[j-1].pe_if.tx[NORTH];
          assign pe_x[i].pe_y[j].pe_if.clock_rx[SOUTH] = pe_x[i].pe_y[j-1].pe_if.clock_tx[NORTH];

          assign pe_x[i].pe_y[j-1].pe_if.data_i[NORTH][FLIT_WIDTH-1:0] = pe_x[i].pe_y[j].pe_if.data_o[SOUTH][FLIT_WIDTH-1:0];
          assign pe_x[i].pe_y[j-1].pe_if.credit_i[NORTH] = pe_x[i].pe_y[j].pe_if.credit_o[SOUTH];
          assign pe_x[i].pe_y[j-1].pe_if.rx[NORTH] = pe_x[i].pe_y[j].pe_if.tx[SOUTH];
          assign pe_x[i].pe_y[j-1].pe_if.clock_rx[NORTH] = pe_x[i].pe_y[j].pe_if.clock_tx[SOUTH];
        end 

        if(j == NOC_DIM_Y-1) begin

          $info("mesh connection (%0d, %0d) NORTH => grounded", i, j);

          // grounding north border
          assign pe_x[i].pe_y[j].pe_if.data_i[NORTH][FLIT_WIDTH-1:0] = 0;
          assign pe_x[i].pe_y[j].pe_if.credit_i[NORTH] = 1'b0;
          assign pe_x[i].pe_y[j].pe_if.rx[NORTH] = 1'b0;
          assign pe_x[i].pe_y[j].pe_if.clock_rx[NORTH] = 1'b0;
        end
      end
    end
  endgenerate
        
endmodule: manycore_top
