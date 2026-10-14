// DDMA send (hw/ddma/ddma.sv, header, size and payload flits).
//
// Hermes LOCAL port protocol: the router accepts a flit on the edge
// where rx = 1 and credit_o = 1. The DDMA keeps each flit on data_i with
// rx = 1 until that edge and leaves SENDING_HEADER, SENDING_SIZE and
// SENDING_PAYLOAD_DELAYER only on acceptance, so no flit is lost when the
// LOCAL buffer is full.
//
// The router model below reproduces the Hermes credit
// (credit_o = occupancy < 8) and drains the buffer following a
// pseudorandom pattern. The scoreboard compares the accepted flits with
// [destination, size, payload...]. The scenario without backpressure also
// checks the timing: header accepted 2 cycles after the command, tail 10
// cycles after the command with p = 6.
`timescale 1ns/100ps
module tb_ddma_send;
  import orca_pkg::*;
  bit clock = 0; bit reset = 1;
  always #1 clock = ~clock;
  integer cyc = 0;
  always @(posedge clock) cyc <= cyc + 1;

  interface_router_port #(32) rp(clock, reset);
  interface_memory #(32) mdma(clock, reset);
  interface_memory #(32) mcpu(clock, reset);
  interface_ddma #(32,32,10,0) dif(clock, reset);
  dual_port_ram #(32, 1025) mem(.clock(clock), .reset(reset), .enable(1'b1),
    .mem_if_a(mdma.MEM), .mem_if_b(mcpu.MEM));
  ddma #(32,32,10,0,4096) dut(.clock(clock), .reset(reset), .router_if(rp.DDMA),
    .mem_if(mdma.DUT), .ddma_if(dif.DDMA));

  // ---------------- model of the router LOCAL port ----------------
  integer occ = 0;            // flits in the buffer (includes flits of another packet)
  integer drain_start = 0;    // cycle from which the buffer drains
  integer drain_pct = 100;    // probability of removing one flit per cycle
  integer nacc = 0;
  logic [31:0] acc [0:63];
  integer acc_cyc [0:63];
  bit recording = 0;

  assign rp.credit_o = (occ < 8);
  always @(posedge clock) begin
    automatic integer n = occ;
    if (recording && rp.rx && occ < 8) begin
      acc[nacc] = rp.data_i; acc_cyc[nacc] = cyc; nacc = nacc + 1; n = n + 1;
    end
    if (cyc >= drain_start && n > 0 && ($urandom % 100) < drain_pct) n = n - 1;
    occ <= n;
  end

  // ---------------- router output port (reception) ----------------
  // presents [destination, size, payload] with tx = 1; the flit leaves on the edge
  // where tx = 1 and credit_i = 1
  logic [31:0] rxq [0:63];
  integer rxn = 0, rxi = 0;
  bit rx_active = 0;
  always @(posedge clock) begin
    if (rx_active && rp.tx && rp.credit_i) rxi = rxi + 1;
    if (rx_active && rxi < rxn) begin rp.tx <= 1; rp.data_o <= rxq[rxi]; end
    else rp.tx <= 0;
  end

  // CPU: answers the reception interrupts after a few cycles
  bit cpu_active = 0;
  always @(negedge clock) begin
    if (cpu_active && dif.irq_recv_size_out) begin
      repeat (5) @(negedge clock);
      dif.recv_addr_in = 32'h40000100;
      dif.recv_cmd_in = ~dif.recv_cmd_in;
      wait (!dif.irq_recv_size_out);
    end
    if (cpu_active && dif.irq_recv_hshk_out) begin
      repeat (3) @(negedge clock);
      dif.recv_cmd_in = ~dif.recv_cmd_in;
      wait (!dif.irq_recv_hshk_out);
    end
  end

  integer errors = 0;
  localparam logic [31:0] DEST = 32'h0101;
  localparam int Q = 24;   // payload flits received in the concurrent scenario

  task automatic run_case(input integer occ0, input integer dstart,
                          input integer dpct, input bit check_timing,
                          input integer P = 6, input bit with_rx = 0);
    integer cmd_cyc, k;
    reset = 1; recording = 0;
    repeat (3) @(negedge clock);
    occ = occ0; nacc = 0;
    drain_start = cyc + dstart; drain_pct = dpct;
    dif.send_cmd_in = 0;
    rx_active = 0; rxi = 0; rxn = 0; cpu_active = 0;
    @(negedge clock); reset = 0;
    repeat (2) @(negedge clock);
    if (with_rx) begin
      rxq[0] = 32'h0000; rxq[1] = Q;
      for (int i = 0; i < Q; i++) rxq[i + 2] = 32'hB000 + i;
      for (int i = 0; i < Q; i++) mem.mem[32'h40 + i] = 0;
      rxn = Q + 2; rx_active = 1; cpu_active = 1;
    end
    recording = 1;
    dif.send_dest_in = DEST; dif.send_addr_in = 32'h40000000; dif.send_size_in = P;
    dif.send_cmd_in = 1; cmd_cyc = cyc;
    k = 0;
    while (dut.sstate != 8'b0100_0000 && k < 2000) begin @(negedge clock); k++; end
    @(negedge clock);
    dif.send_cmd_in = 0;
    repeat (3) @(negedge clock);
    recording = 0;
    if (with_rx) begin
      k = 0;
      while ((rxi < rxn || dut.rstate != 8'b0000_0001) && k < 2000) begin @(negedge clock); k++; end
      for (int i = 0; i < Q; i++)
        if (mem.mem[32'h40 + i] !== 32'hB000 + i) begin
          $display("FAIL rx occ0=%0d: mem[%0d] = %h", occ0, i, mem.mem[32'h40 + i]);
          errors++;
          return;
        end
    end
    if (k >= 2000) begin
      $display("FAIL occ0=%0d dstart=%0d dpct=%0d: timeout", occ0, dstart, dpct);
      errors++;
      return;
    end
    if (nacc != P + 2 || acc[0] !== DEST || acc[1] !== P) begin
      $display("FAIL occ0=%0d dstart=%0d dpct=%0d: %0d flits, header %h, size %h",
               occ0, dstart, dpct, nacc, acc[0], acc[1]);
      errors++;
      return;
    end
    for (int i = 0; i < P; i++)
      if (acc[i + 2] !== 32'hA000 + i) begin
        $display("FAIL occ0=%0d dstart=%0d dpct=%0d: payload[%0d] = %h",
                 occ0, dstart, dpct, i, acc[i + 2]);
        errors++;
        return;
      end
    if (check_timing && (acc_cyc[0] - cmd_cyc != 2 || acc_cyc[P + 1] - cmd_cyc != P + 4)) begin
      $display("FAIL timing: header +%0d (expected +2), tail +%0d (expected +%0d)",
               acc_cyc[0] - cmd_cyc, acc_cyc[P + 1] - cmd_cyc, P + 4);
      errors++;
    end
  endtask

  initial begin
    mcpu.wb_in = 0; mcpu.addr_in = 0; mcpu.data_in = 0;
    dif.send_cmd_in = 0; dif.recv_cmd_in = 0; dif.send_addr_in = 0;
    dif.send_size_in = 0; dif.send_dest_in = 0; dif.recv_addr_in = 0;
    rp.data_o = 0;
    for (int i = 0; i < 48; i++) begin
      @(negedge clock); mcpu.wb_in = 4'hF; mcpu.addr_in = i; mcpu.data_in = 32'hA000 + i;
    end
    @(negedge clock); mcpu.wb_in = 0;

    run_case(0, 0, 100, 1);                       // no backpressure
    for (int o = 0; o <= 8; o++)                  // buffer with o flits of another packet
      for (int d = 0; d <= 12; d += 3)            // draining starts d cycles later
        run_case(o, d, 100, 0);
    for (int s = 0; s < 200; s++)                 // esvaziamento intermitente
      run_case($urandom % 9, $urandom % 10, 20 + $urandom % 70, 0);
    for (int s = 0; s < 60; s++)                  // send of 40 flits with reception
      run_case($urandom % 9, $urandom % 10, 20 + $urandom % 80, 0, 40, 1);  // concorrente

    if (errors == 0) $display("PASS tb_ddma_send");
    else $display("FAIL tb_ddma_send: %0d cases", errors);
    $finish;
  end
endmodule
