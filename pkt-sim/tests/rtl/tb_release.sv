// Release generator of manycore_pe.sv on a 4x4 manycore_top
// (RELEASE_MASK, RELEASE_PERIOD_NS, RELEASE_DELAY_NS) and on the default
// 2x2 (application E: PE 0 only).
//
// The PEs run with stubs for the router, core and peripherals
// (pe_stubs.sv); every stub core drives the same bus (tb_bus), so one
// write to 0x2000004C acknowledges the interrupt on every PE.
// Checks: the node index of each PE is y * NOC_DIM_X + x; only the PEs of
// the mask raise wake_up_irq, once per release; the lowest PE of the mask
// is the one that prints the TRIGGER lines of application E; the 2x2
// defaults enable PE 0 only, with the period and warm-up of run F.
`timescale 1ns/100ps
module tb_release;
  import orca_pkg::*;

  // CAR-V (vscaled mapping): sources FBU1 to FBU8 on PEs 1, 2, 3, 4, 5, 7, 8, 11
  localparam logic [63:0] MASK = 64'h09BE;
  localparam int DELAY = 100, PERIOD = 200, RELEASES = 5;

  manycore_top #(.NOC_DIM_X(4), .NOC_DIM_Y(4), .RELEASE_MASK(MASK),
                 .RELEASE_PERIOD_NS(PERIOD), .RELEASE_DELAY_NS(DELAY)) m44();
  manycore_top m22();   // defaults: 2x2, PE 0

  int rises44 [16];
  logic [15:0] irq44;
  int rises22 [4];
  integer errors = 0;

  genvar gx, gy;
  generate
    for (gx = 0; gx < 4; gx++) begin : mx
      for (gy = 0; gy < 4; gy++) begin : my
        logic prev = 0;
        assign irq44[gy * 4 + gx] = m44.pe_x[gx].pe_y[gy].pe_mod.wake_up_irq;
        always @(posedge m44.clock) begin
          if (!m44.reset && m44.pe_x[gx].pe_y[gy].pe_mod.wake_up_irq && !prev) rises44[gy * 4 + gx]++;
          prev <= m44.pe_x[gx].pe_y[gy].pe_mod.wake_up_irq;
        end
        initial begin
          #1;
          if (m44.pe_x[gx].pe_y[gy].pe_mod.NODE_INDEX != gy * 4 + gx) begin
            $display("FAIL node index of (%0d,%0d) = %0d", gx, gy, m44.pe_x[gx].pe_y[gy].pe_mod.NODE_INDEX);
            errors++;
          end
          if (m44.pe_x[gx].pe_y[gy].pe_mod.RELEASE_HERE != MASK[gy * 4 + gx]) begin
            $display("FAIL RELEASE_HERE of (%0d,%0d)", gx, gy); errors++;
          end
          if (m44.pe_x[gx].pe_y[gy].pe_mod.RELEASE_FIRST != (gy * 4 + gx == 1)) begin
            $display("FAIL RELEASE_FIRST of (%0d,%0d)", gx, gy); errors++;
          end
        end
      end
    end
    for (gx = 0; gx < 2; gx++) begin : dx
      for (gy = 0; gy < 2; gy++) begin : dy
        logic prev = 0;
        initial begin
          #1;
          if (m22.pe_x[gx].pe_y[gy].pe_mod.RELEASE_HERE != (gx == 0 && gy == 0)) begin
            $display("FAIL 2x2 RELEASE_HERE of (%0d,%0d)", gx, gy); errors++;
          end
        end
        always @(posedge m22.clock) begin
          if (!m22.reset && m22.pe_x[gx].pe_y[gy].pe_mod.wake_up_irq && !prev) rises22[gy * 2 + gx]++;
          prev <= m22.pe_x[gx].pe_y[gy].pe_mod.wake_up_irq;
        end
      end
    end
  endgenerate

  // the "kernel": acknowledges a raised interrupt (irq4_handler flips 0x2000004C)
  logic flip = 0;
  logic any_irq;
  assign any_irq = |irq44;

  initial begin
    tb_bus::addr = 32'h40000000; tb_bus::wb = 0;
    while ($time < DELAY + RELEASES * PERIOD - PERIOD / 2) begin
      @(negedge m44.clock);
      if (any_irq || m22.pe_x[0].pe_y[0].pe_mod.wake_up_irq) begin
        repeat (5) @(negedge m44.clock);
        flip = ~flip;
        tb_bus::addr = 32'h2000004C; tb_bus::data = endianess({31'b0, flip}); tb_bus::wb = 4'hF;
        @(negedge m44.clock);
        tb_bus::wb = 0; tb_bus::addr = 32'h40000000;
        repeat (4) @(negedge m44.clock);
      end
    end
    for (int k = 0; k < 16; k++) begin
      if (rises44[k] != (MASK[k] ? RELEASES : 0)) begin
        $display("FAIL 4x4 PE %0d: %0d releases (expected %0d)", k, rises44[k], MASK[k] ? RELEASES : 0);
        errors++;
      end
    end
    // 2x2 defaults: first release at 3 ms (after this test), every 0.5 ms
    for (int k = 0; k < 4; k++) begin
      if (rises22[k] != 0) begin
        $display("FAIL 2x2 PE %0d: %0d releases before 3 ms", k, rises22[k]); errors++;
      end
    end
    if (m22.pe_x[0].pe_y[0].pe_mod.wake_up_alarm != 500_000 || m22.pe_x[0].pe_y[0].pe_mod.wake_up_delay != 3_000_000) begin
      $display("FAIL 2x2 period %0d ns, delay %0d ns", m22.pe_x[0].pe_y[0].pe_mod.wake_up_alarm,
               m22.pe_x[0].pe_y[0].pe_mod.wake_up_delay);
      errors++;
    end
    if (m22.pe_x[0].pe_y[0].pe_mod.RELEASE_FIRST != 1) begin $display("FAIL 2x2 RELEASE_FIRST"); errors++; end
    if (errors == 0) $display("PASS tb_release");
    else $display("FAIL tb_release: %0d errors", errors);
    $finish;
  end
endmodule
