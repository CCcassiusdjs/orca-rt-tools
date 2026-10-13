// Release generator of manycore_pe.sv (PE 0-0) at a clock given by its
// half period in fs (manycore_top.sv, CLOCK_HALF_PERIOD_FS).
//
// The release of A is due at cycle W + k R and the controller sees it at
// the rising edge of that cycle (wake_up_cycle >= wake_up_counter_next);
// the interrupt rises one edge later and stays up until the processor
// writes the acknowledge register (0x2000004C). The test checks, for the
// half period HALF_FS:
//   1. the interrupt rises after edge W + k R + 1 (k = 0 to 3), whatever
//      the instant of the acknowledge;
//   2. rising edge n occurs at (2 n + 1) HALF_FS fs (timescale 1ns/1fs
//      keeps the half period exact; 1ns/100ps rounds 1.148897 ns to 1.1);
//   3. cycle_ns(c), the instant of the TRIGGER line, is floor(2 c HALF_FS / 1e6).
// run.sh runs it with HALF_FS = 1000000 (500 MHz) and 1148897 (435.2 MHz).
`timescale 1ns/1fs
module tb_release #(parameter longint HALF_FS = 1148897);
  import orca_pkg::*;
  localparam longint R = 40, W = 100;
  bit clock = 0; bit reset = 1;
  always #(HALF_FS * 1fs) clock = ~clock;
  always #(4 * HALF_FS * 1fs) reset = 0;

  localparam DX = 2, DY = 2;
  localparam ADDRESS = (DX << 24) | (DY << 16);   // PE 0-0: the controller runs

  interface_pe #(32, 32) pe_if(clock, reset);
  manycore_pe #(32, 32, 4096, 4096, ADDRESS, 10, DX, DY, HALF_FS, R, W) dut(
    .clock(clock), .reset(reset), .pe_if(pe_if.PE));

  assign pe_if.clock_rx = '0;
  assign pe_if.rx = '0;
  assign pe_if.credit_i = '1;
  assign pe_if.data_i = '0;

  integer errors = 0;
  longint edges = 0;      // rising edges so far
  longint rise[4];
  integer k = 0;
  bit irq_prev = 0;
  logic [31:0] flip = 0;

  real t_ns;
  longint t_fs;
  always @(posedge clock) begin
    edges <= edges + 1;
    // 2: instant of edge n = edges (before the update); the cast rounds
    t_ns = $realtime;
    t_fs = longint'(t_ns * 1e6);
    if (edges == W + 3 * R && t_fs != (2 * edges + 1) * HALF_FS) begin
      $display("FAIL edge %0d at %0d fs, expected %0d fs", edges, t_fs, (2 * edges + 1) * HALF_FS);
      errors++;
    end
  end

  always @(negedge clock) begin
    if (dut.wake_up_irq && !irq_prev && k < 4) begin
      rise[k] = edges;    // edges so far, the one that raised the interrupt included
      k++;
    end
    irq_prev = dut.wake_up_irq;
  end

  task automatic ack();
    @(negedge clock);
    flip = flip ^ 1;
    tb_bus::addr = 32'h2000004C; tb_bus::data = endianess(flip); tb_bus::wb = 4'hF;
    @(negedge clock);
    tb_bus::wb = 0; tb_bus::addr = 32'h40000000;
  endtask

  initial begin
    tb_bus::addr = 32'h40000000;
    for (int i = 0; i < 4; i++) begin
      wait (k > i);
      // acknowledge after a delay that differs per release
      repeat (3 + 5 * i) @(negedge clock);
      ack();
    end
    for (int i = 0; i < 4; i++)
      // edges 0 to W + i R + 1 have passed: W + i R + 2 edges
      if (rise[i] != W + i * R + 2) begin
        $display("FAIL release %0d: interrupt after %0d edges, expected %0d", i, rise[i], W + i * R + 2);
        errors++;
      end
    if (dut.cycle_ns(W + R) != (2 * (W + R) * HALF_FS) / 1_000_000) begin
      $display("FAIL cycle_ns(%0d) = %0d", W + R, dut.cycle_ns(W + R)); errors++;
    end
    if (errors == 0) $display("PASS tb_release HALF_FS=%0d", HALF_FS);
    else $display("FAIL tb_release HALF_FS=%0d: %0d errors", HALF_FS, errors);
    $finish;
  end
endmodule
