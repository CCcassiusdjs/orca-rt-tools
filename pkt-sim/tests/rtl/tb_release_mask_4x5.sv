// Release generator of manycore_pe.sv on the 4x5 manycore_top of the
// composition of CAR-V and application E (experiments/multiapp,
// app/carv_e.sim: RELEASE_MASK = 88462, PEs 1, 2, 3, 7, 8, 11, 12, 16 of
// CAR-V and PE 14 of E).
//
// Same setup as tb_release_mask.sv (stubs of pe_stubs.sv, one bus for the
// acknowledgment of every PE, short warm-up and period). Checks: the node
// index of each PE is y * NOC_DIM_X + x for y up to 4 (a mesh with more
// rows than columns); only the PEs of the mask raise wake_up_irq, once per
// release; PE 1 (the lowest PE of the mask) prints the TRIGGER lines.
`timescale 1ns/1fs
module tb_release_mask_4x5;
  import orca_pkg::*;

  localparam logic [63:0] MASK = 64'd88462;
  localparam int W = 4, H = 5, N = W * H;
  localparam int DELAY = 100, PERIOD = 200, RELEASES = 5;

  manycore_top #(.NOC_DIM_X(W), .NOC_DIM_Y(H), .RELEASE_MASK(MASK),
                 .WARMUP_CYCLES(DELAY / 2), .RELEASE_CYCLES(PERIOD / 2)) m();

  int rises [N];
  logic [N-1:0] irq;
  integer errors = 0;

  genvar gx, gy;
  generate
    for (gx = 0; gx < W; gx++) begin : mx
      for (gy = 0; gy < H; gy++) begin : my
        logic prev = 0;
        assign irq[gy * W + gx] = m.pe_x[gx].pe_y[gy].pe_mod.wake_up_irq;
        always @(posedge m.clock) begin
          if (!m.reset && m.pe_x[gx].pe_y[gy].pe_mod.wake_up_irq && !prev) rises[gy * W + gx]++;
          prev <= m.pe_x[gx].pe_y[gy].pe_mod.wake_up_irq;
        end
        initial begin
          #1;
          if (m.pe_x[gx].pe_y[gy].pe_mod.NODE_INDEX != gy * W + gx) begin
            $display("FAIL node index of (%0d,%0d) = %0d", gx, gy, m.pe_x[gx].pe_y[gy].pe_mod.NODE_INDEX);
            errors++;
          end
          if (m.pe_x[gx].pe_y[gy].pe_mod.RELEASE_HERE != MASK[gy * W + gx]) begin
            $display("FAIL RELEASE_HERE of (%0d,%0d)", gx, gy); errors++;
          end
          if (m.pe_x[gx].pe_y[gy].pe_mod.RELEASE_FIRST != (gy * W + gx == 1)) begin
            $display("FAIL RELEASE_FIRST of (%0d,%0d)", gx, gy); errors++;
          end
        end
      end
    end
  endgenerate

  // the "kernel": acknowledges a raised interrupt (irq4_handler flips 0x2000004C)
  logic flip = 0;

  initial begin
    tb_bus::addr = 32'h40000000; tb_bus::wb = 0;
    while ($time < DELAY + RELEASES * PERIOD - PERIOD / 2) begin
      @(negedge m.clock);
      if (|irq) begin
        repeat (5) @(negedge m.clock);
        flip = ~flip;
        tb_bus::addr = 32'h2000004C; tb_bus::data = endianess({31'b0, flip}); tb_bus::wb = 4'hF;
        @(negedge m.clock);
        tb_bus::wb = 0; tb_bus::addr = 32'h40000000;
        repeat (4) @(negedge m.clock);
      end
    end
    for (int k = 0; k < N; k++) begin
      if (rises[k] != (MASK[k] ? RELEASES : 0)) begin
        $display("FAIL 4x5 PE %0d: %0d releases (expected %0d)", k, rises[k], MASK[k] ? RELEASES : 0);
        errors++;
      end
    end
    if (errors == 0) $display("PASS tb_release_mask_4x5");
    else $display("FAIL tb_release_mask_4x5: %0d errors", errors);
    $finish;
  end
endmodule
