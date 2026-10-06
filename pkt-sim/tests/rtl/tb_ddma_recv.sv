// Fixes 21 and 22 (hw/ddma/ddma.sv, reception).
//
// 21. Reception timing without memory contention: same as the
//     original version. Values measured in the original (commit 4c299fc) with
//     P = 6: header +2, size +4, irq_size +4 (from arrival);
//     payload[0] +4, last payload +P+3, irq_hshk +P+4 (from the
//     CPU acknowledgment). The fix of the reception path with concurrent
//     sending is tested in tb_ddma_send (scenario with reception).
// 22. Destination check (TODO in ddma.sv:356): a packet with a destination
//     different from ADDRESS is consumed without a memory write and without
//     an interrupt; the next packet arrives normally.
`timescale 1ns/100ps
module tb_ddma_recv;
  import orca_pkg::*;
  bit clock = 0; bit reset = 1;
  always #1 clock = ~clock;
  integer cyc = 0;
  always @(posedge clock) cyc <= cyc + 1;

  localparam logic [31:0] ADDR = 32'h0201;   // node (2,1)
  interface_router_port #(32) rp(clock, reset);
  interface_memory #(32) mdma(clock, reset);
  interface_memory #(32) mcpu(clock, reset);
  interface_ddma #(32,32,10,ADDR) dif(clock, reset);
  dual_port_ram #(32, 1025) mem(.clock(clock), .reset(reset), .enable(1'b1),
    .mem_if_a(mdma.MEM), .mem_if_b(mcpu.MEM));
  ddma #(32,32,10,ADDR,4096) dut(.clock(clock), .reset(reset), .router_if(rp.DDMA),
    .mem_if(mdma.DUT), .ddma_if(dif.DDMA));

  assign rp.credit_o = 1;

  // router output port
  logic [31:0] rxq [0:127];
  integer rxn = 0, rxi = 0, ncons = 0;
  integer cons_cyc [0:127];
  always @(posedge clock) begin
    if (rp.tx && rp.credit_i) begin cons_cyc[rxi] = cyc; rxi = rxi + 1; end
    if (rxi < rxn) begin rp.tx <= 1; rp.data_o <= rxq[rxi]; end
    else rp.tx <= 0;
  end

  integer irq_size_cyc = -1, irq_hshk_cyc = -1, nirq_size = 0;
  always @(posedge clock) begin
    if (dif.irq_recv_size_out && irq_size_cyc < 0) begin irq_size_cyc = cyc; nirq_size++; end
    if (dif.irq_recv_hshk_out && irq_hshk_cyc < 0) irq_hshk_cyc = cyc;
  end

  integer errors = 0;
  localparam int P = 6;
  localparam int CPU_DELAY = 20;

  task automatic push_packet(input logic [31:0] dest, input integer n, input logic [31:0] base);
    rxq[rxn] = dest; rxq[rxn + 1] = n;
    for (int i = 0; i < n; i++) rxq[rxn + 2 + i] = base + i;
    rxn = rxn + n + 2;
  endtask

  integer t0, ack_cyc;
  initial begin
    mcpu.wb_in = 0; mcpu.addr_in = 0; mcpu.data_in = 0;
    dif.send_cmd_in = 0; dif.recv_cmd_in = 0; dif.send_addr_in = 0;
    dif.send_size_in = 0; dif.send_dest_in = 0; dif.recv_addr_in = 0;
    rp.data_o = 0;
    for (int i = 0; i < 256; i++) mem.mem[i] = 32'hDEAD0000 + i;
    repeat (4) @(negedge clock); reset = 0;
    repeat (2) @(negedge clock);

    // ---- 21: timing ----
    t0 = cyc;
    push_packet(ADDR, P, 32'hB000);
    wait (dif.irq_recv_size_out);
    repeat (CPU_DELAY) @(negedge clock);
    dif.recv_addr_in = 32'h40000100; dif.recv_cmd_in = ~dif.recv_cmd_in; ack_cyc = cyc;
    wait (dif.irq_recv_hshk_out);
    @(negedge clock); dif.recv_cmd_in = ~dif.recv_cmd_in;
    repeat (4) @(negedge clock);
    $display("timing: header +%0d size +%0d irq_size +%0d | payload0 +%0d payload_last +%0d irq_hshk +%0d (from ack)",
      cons_cyc[0] - t0, cons_cyc[1] - t0, irq_size_cyc - t0,
      cons_cyc[2] - ack_cyc, cons_cyc[P + 1] - ack_cyc, irq_hshk_cyc - ack_cyc);
    for (int i = 0; i < P; i++)
      if (mem.mem[64 + i] !== 32'hB000 + i) begin
        $display("FAIL payload mem[%0d] = %h", 64 + i, mem.mem[64 + i]); errors++;
      end
    if (cons_cyc[0] - t0 != 2 || cons_cyc[1] - t0 != 4 || irq_size_cyc - t0 != 4
        || cons_cyc[2] - ack_cyc != 4 || cons_cyc[P + 1] - ack_cyc != P + 3
        || irq_hshk_cyc - ack_cyc != P + 4) begin
      $display("FAIL timing"); errors++;
    end

    // ---- 22: packet for another node ----
    irq_size_cyc = -1; irq_hshk_cyc = -1; nirq_size = 0;
    push_packet(32'h0203, 5, 32'hC000);          // destino (2,3)
    push_packet(ADDR, 3, 32'hD000);              // next packet, valid
    wait (dif.irq_recv_size_out);
    if (dif.recv_size_out != 3) begin
      $display("FAIL drop: first irq has size %0d (foreign packet raised irq)", dif.recv_size_out); errors++;
    end
    repeat (CPU_DELAY) @(negedge clock);
    dif.recv_addr_in = 32'h40000200; dif.recv_cmd_in = ~dif.recv_cmd_in;
    wait (dif.irq_recv_hshk_out);
    @(negedge clock); dif.recv_cmd_in = ~dif.recv_cmd_in;
    repeat (4) @(negedge clock);
    if (rxi != rxn) begin $display("FAIL drop: %0d of %0d flits consumed", rxi, rxn); errors++; end
    for (int i = 0; i < 3; i++)
      if (mem.mem[128 + i] !== 32'hD000 + i) begin
        $display("FAIL drop: mem[%0d] = %h", 128 + i, mem.mem[128 + i]); errors++;
      end
    for (int i = 0; i < 256; i++)
      if (!(i >= 64 && i < 64 + P) && !(i >= 128 && i < 131) && mem.mem[i] !== 32'hDEAD0000 + i) begin
        $display("FAIL drop: stray write mem[%0d] = %h", i, mem.mem[i]); errors++;
      end

    if (errors == 0) $display("PASS tb_ddma_recv");
    else $display("FAIL tb_ddma_recv: %0d errors", errors);
    $finish;
  end
endmodule
