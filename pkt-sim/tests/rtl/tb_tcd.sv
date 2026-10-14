// Hyperperiod counter of the TCD (hw/tcd/tcd.sv).
//
// The counter runs 0, 1, ..., HYPERPERIOD - 1 and returns to 0, so the
// TCNI prototype releases each configuration at its instant.
//
// tcd uses the DDMA interface from 2023-03 (addr_in, nbytes_in, cmd_in,
// status_out), absent from the current version. This test declares that
// interface locally (legacy_ddma_if.svh) to compile the module.
`timescale 1ns/100ps
module tb_tcd;
  bit clock = 0; bit reset = 1;
  always #1 clock = ~clock;

  interface_tcd #(32) tif(clock, reset);
  interface_ddma dif(clock, reset);
  tcd #(32) dut(.clock(clock), .reset(reset), .tcd_if(tif.TCD), .ddma_if(dif.TCD));

  integer errors = 0;
  integer seen [0:19];
  integer cmd_timer = -1;

  initial begin
    tif.input_in = 0; tif.data_in = 0; dif.status_out = 1;
    repeat (3) @(negedge clock); reset = 0;

    // counter sequence: 0..19 and wrap to 0
    for (int i = 0; i < 20; i++) seen[i] = 0;
    @(negedge clock);
    for (int c = 0; c < 45; c++) begin
      if (dut.timer < 0 || dut.timer > 19) begin
        $display("FAIL timer out of range: %0d", dut.timer); errors++;
      end else seen[dut.timer]++;
      @(negedge clock);
    end
    for (int i = 0; i < 20; i++)
      if (seen[i] < 2) begin $display("FAIL timer never reached %0d twice", i); errors++; end

    // configuration: address, size, instant 7
    tif.input_in = 1; tif.data_in = 32'h40000000; @(negedge clock);
    tif.data_in = 6;           @(negedge clock);
    tif.data_in = 7;           @(negedge clock);
    tif.input_in = 0;
    for (int c = 0; c < 45 && cmd_timer < 0; c++) begin
      @(posedge clock); #0.1;
      if (dif.cmd_in) cmd_timer = dut.timer;
    end
    if (cmd_timer < 0) begin $display("FAIL cmd_in never raised"); errors++; end
    else if (cmd_timer != 8) begin
      // cmd_in rises in the cycle after the configured instant
      $display("FAIL cmd_in raised at timer %0d (expected 8)", cmd_timer); errors++;
    end
    if (dif.addr_in !== 32'h40000000 || dif.nbytes_in !== 6) begin
      $display("FAIL ddma config addr %h size %0d", dif.addr_in, dif.nbytes_in); errors++;
    end

    if (errors == 0) $display("PASS tb_tcd");
    else $display("FAIL tb_tcd: %0d errors", errors);
    $finish;
  end
endmodule
