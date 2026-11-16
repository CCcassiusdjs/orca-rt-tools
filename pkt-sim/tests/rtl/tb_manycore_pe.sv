// PE of the manycore (manycore_modelsim/manycore_pe.sv).
//
// 1. addr_x() reads ADDRESS[15:8] and addr_y() reads ADDRESS[7:0], the
//    format of manycore_top.sv; the logs "X-Y scheduled" and the
//    output-X-Y.txt files carry X first.
// 2. The register read (always_comb) uses blocking assignments and assigns
//    cpu_if.data_in in every branch; verilator --lint-only (run.sh) reports
//    no COMBDLY and no LATCH.
// 3. The reset clears cacc_reg and cacc_counter to cacc_counter_4 (no X in
//    ModelSim, no random value in Verilator with --x-initial unique).
//
// Iteration marker (0x2000003C, device/cacc.h): cleared by the reset, read
// back, and printed as `<t> <x-y> ITER begin|end <task> <k>`; the test in
// orca-rt-tools/tests/test_rtl.py parses the two printed lines.
//
// The PE runs with stubs for the router, core and peripherals (pe_stubs.sv).
`timescale 1ns/100ps
module tb_manycore_pe;
  import orca_pkg::*;
  bit clock = 0; bit reset = 1;
  always #1 clock = ~clock;

  localparam X = 2, Y = 1, DX = 3, DY = 2;
  localparam ADDRESS = (DX << 24) | (DY << 16) | (X << 8) | Y;

  interface_pe #(32, 32) pe_if(clock, reset);
  manycore_pe #(32, 32, 4096, 4096, ADDRESS, 10, DX, DY) dut(
    .clock(clock), .reset(reset), .pe_if(pe_if.PE));

  assign pe_if.clock_rx = '0;
  assign pe_if.rx = '0;
  assign pe_if.credit_i = '1;
  assign pe_if.data_i = '0;

  integer errors = 0;

  task automatic bus_write(input logic [31:0] a, input logic [31:0] d);
    @(negedge clock);
    tb_bus::addr = a; tb_bus::data = endianess(d); tb_bus::wb = 4'hF;
    @(negedge clock);
    tb_bus::wb = 0; tb_bus::addr = 32'h40000000;
  endtask

  task automatic bus_read(input logic [31:0] a, output logic [31:0] d);
    @(negedge clock);
    tb_bus::addr = a; tb_bus::wb = 0;
    @(negedge clock);                 // address registered (dly_address)
    d = endianess(dut.cpu_if.data_in);
    tb_bus::addr = 32'h40000000;
  endtask

  logic [31:0] v;
  initial begin
    repeat (4) @(negedge clock); reset = 0;
    repeat (2) @(negedge clock);

    // 27: counters cleared by the reset
    bus_read(32'h20000030, v); if (v !== 0) begin $display("FAIL reset cacc_counter_2 = %h", v); errors++; end
    bus_read(32'h20000034, v); if (v !== 0) begin $display("FAIL reset cacc_counter_3 = %h", v); errors++; end
    bus_read(32'h20000038, v); if (v !== 0) begin $display("FAIL reset cacc_counter_4 = %h", v); errors++; end
    bus_read(32'h2000003C, v); if (v !== 0) begin $display("FAIL reset cacc_iter = %h", v); errors++; end

    // 25: node coordinates
    if (dut.addr_x() != X || dut.addr_y() != Y) begin
      $display("FAIL addr_x() = %0d, addr_y() = %0d (expected %0d, %0d)", dut.addr_x(), dut.addr_y(), X, Y);
      errors++;
    end
    if (dut.log_filename() != "../logs/output-2-1.txt") begin
      $display("FAIL log_filename() = %s", dut.log_filename()); errors++;
    end

    // 26: register read and write through the bus
    bus_write(32'h20000028, 32'h12345678);
    bus_read(32'h20000028, v); if (v !== 32'h12345678) begin $display("FAIL cacc_reg = %h", v); errors++; end
    bus_write(32'h20000030, 7);
    bus_read(32'h20000030, v); if (v !== 7) begin $display("FAIL cacc_counter_2 = %h", v); errors++; end
    bus_read(32'h20000000, v); if (v !== ADDRESS) begin $display("FAIL node address reg = %h", v); errors++; end

    // iteration marker: begin of E, iteration 5; end of J, iteration 70000
    bus_write(32'h2000003C, 32'h45000005);
    bus_read(32'h2000003C, v); if (v !== 32'h45000005) begin $display("FAIL cacc_iter = %h", v); errors++; end
    bus_write(32'h2000003C, 32'hCA011170);

    if (errors == 0) $display("PASS tb_manycore_pe");
    else $display("FAIL tb_manycore_pe: %0d errors", errors);
    $finish;
  end
endmodule
