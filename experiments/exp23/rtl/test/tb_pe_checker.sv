// Testbench of the flit times of pe_checker.sv (Verilator, no DUT).
//
// Two PE stubs, each with a memory named memory_mod (the monitor reads
// memory_mod.mem, as in manycore_pe) and a pe_checker on its LOCAL port
// signals. The testbench plays the router and the DDMA: it sends two
// packets from (0,0) to (1,0) of a 2x2 mesh and drives, per edge, the
// handshakes of both LOCAL ports with known blocks, gaps and stalls.
// tests/test_exp23_flit_monitor.py builds it, runs it and checks the
// FLIT lines against the schedule below.
//
// Packet 1: tag 18 (payload 20 bytes, p = 3 + 5 = 8 flits), 10 flits.
//   TX: header accepted at edge H1; credit_o = 0 on 2 edges before flit 3
//       (block = 2); rx = 0 on 1 edge before flit 5 (gap = 1).
//   RX: header on data_o 12 edges after H1 (m = 1: 6(m+1)); credit_i = 0
//       on the first edge (registered credit, stall 1); after the size
//       flit, 7 edges with tx = 1 and credit_i = 0 (stall 7, the address
//       of irq2); 2 edges with tx = 0 before flit 6 (gap 2).
// Packet 2: tag 5 (payload 8 bytes, p = 3 + 2 = 5 flits), 7 flits; no
//   block or gap; stall 1 (registered credit of the header only); header
//   on data_o 12 edges after its TX header.
`timescale 1ns/100ps

module mem_stub;
  logic [31:0] mem [0:1023];
endmodule

module pe_stub #(parameter int ADDRESS = 0) (
  input logic        clock, reset,
  input logic        rx, credit_o, tx, credit_i,
  input logic [31:0] data_i, data_o,
  input logic        send_cmd_in,
  input logic [31:0] send_dest_in, send_addr_in, send_size_in,
  input logic [31:0] recv_addr_in,
  input logic        recv_cmd_in,
  input logic [3:0]  wb_in,
  input logic [31:0] mem_addr_in, mem_data_in
);
  mem_stub memory_mod();
  pe_checker #(.ADDRESS(ADDRESS), .RAM_MSIZE(4096)) chk (
    .clock(clock), .reset(reset), .rx(rx), .credit_o(credit_o), .data_i(data_i),
    .tx(tx), .credit_i(credit_i), .data_o(data_o),
    .send_cmd_in(send_cmd_in), .send_dest_in(send_dest_in), .send_addr_in(send_addr_in),
    .send_size_in(send_size_in), .recv_addr_in(recv_addr_in), .recv_cmd_in(recv_cmd_in),
    .wb_in(wb_in), .mem_addr_in(mem_addr_in), .mem_data_in(mem_data_in));
endmodule

module tb_pe_checker;
  localparam int DIMX = 2, DIMY = 2;
  localparam int SRC = (DIMX << 24) | (DIMY << 16) | (0 << 8) | 0;   // (0,0), id 0
  localparam int DST = (DIMX << 24) | (DIMY << 16) | (1 << 8) | 0;   // (1,0), id 1
  localparam int BASE = 32'h100;    // send buffer (bytes)
  localparam int RBASE = 32'h400;   // receive buffer (bytes)

  bit clock = 0;
  bit reset = 1;
  always #1 clock = ~clock;

  // source LOCAL port (DDMA -> router) and destination LOCAL port (router -> DDMA)
  logic        s_rx = 0, s_credit = 1, s_cmd = 0;
  logic [31:0] s_data = 0, s_dest = 0, s_addr = 0, s_size = 0;
  logic        d_tx = 0, d_credit = 0, d_rcmd = 0;
  logic [31:0] d_data = 0, d_raddr = 0;
  logic [3:0]  d_wb = 0;
  logic [31:0] d_maddr = 0, d_mdata = 0;

  pe_stub #(SRC) src (.clock(clock), .reset(reset), .rx(s_rx), .credit_o(s_credit), .tx(1'b0), .credit_i(1'b0),
                      .data_i(s_data), .data_o(32'h0), .send_cmd_in(s_cmd), .send_dest_in(s_dest),
                      .send_addr_in(s_addr), .send_size_in(s_size), .recv_addr_in(32'h0), .recv_cmd_in(1'b0),
                      .wb_in(4'h0), .mem_addr_in(32'h0), .mem_data_in(32'h0));
  pe_stub #(DST) dst (.clock(clock), .reset(reset), .rx(1'b0), .credit_o(1'b0), .tx(d_tx), .credit_i(d_credit),
                      .data_i(32'h0), .data_o(d_data), .send_cmd_in(1'b0), .send_dest_in(32'h0),
                      .send_addr_in(32'h0), .send_size_in(32'h0), .recv_addr_in(d_raddr), .recv_cmd_in(d_rcmd),
                      .wb_in(d_wb), .mem_addr_in(d_maddr), .mem_data_in(d_mdata));

  // word image of a 16-bit field pair as the core stores it (byte 0 in 31:24)
  function automatic logic [31:0] pair(input int unsigned lo, input int unsigned hi);
    logic [31:0] v = {hi[15:0], lo[15:0]};
    return {v[7:0], v[15:8], v[23:16], v[31:24]};
  endfunction

  logic [31:0] pkt [0:15];
  int unsigned nflits;

  // packet image in the source memory: [w0 src|dst, w1 ports, w2 size|tag, data]
  task automatic build(input int unsigned tag);
    int unsigned bytes = ((tag + 3) / 4) * 4;
    int unsigned p = 3 + bytes / 4;
    pkt[0] = (1 << 8) | 0;                 // header flit: X = 1, Y = 0
    pkt[1] = p;                            // size flit
    pkt[2] = pair(0, 1);                   // source_node 0, target_node 1
    pkt[3] = pair(7, 9);                   // ports
    pkt[4] = pair(bytes, tag);             // payload_size, tag
    for (int i = 5; i < p + 2; i++) pkt[i] = 32'hA000 + i;
    for (int i = 0; i < p; i++) src.memory_mod.mem[(BASE >> 2) + i] = pkt[i + 2];
    nflits = p + 2;
  endtask

  task automatic edge_();
    @(negedge clock);
  endtask

  // TX of packet with blocks before flit kb (nb edges) and gaps before flit kg (ng edges)
  task automatic send(input int kb, input int nb, input int kg, input int ng);
    s_dest = pkt[0]; s_addr = BASE; s_size = pkt[1]; s_cmd = 1;
    edge_(); s_cmd = 0;
    for (int k = 0; k < nflits; k++) begin
      if (k == kg) begin s_rx = 0; repeat (ng) edge_(); end
      s_rx = 1; s_data = pkt[k];
      if (k == kb) begin s_credit = 0; repeat (nb) edge_(); s_credit = 1; end
      edge_();
    end
    s_rx = 0;
  endtask

  // RX: header present for one edge without credit, then stall ns edges
  // after the size flit and gap ng edges before flit kg
  task automatic recv(input int ns, input int kg, input int ng);
    for (int k = 0; k < nflits; k++) begin
      if (k == kg) begin d_tx = 0; d_credit = 0; repeat (ng) edge_(); end
      d_tx = 1; d_data = pkt[k];
      if (k == 0) begin d_credit = 0; edge_(); end
      if (k == 2 && ns > 0) begin
        // the CPU gives the address before the end of the stall (the DDMA
        // takes the first payload flit two edges after recv_cmd changes)
        d_credit = 0; repeat (ns - 1) edge_(); d_raddr = RBASE; d_rcmd = ~d_rcmd; edge_();
      end
      d_credit = 1;
      d_wb = (k >= 2) ? 4'hF : 4'h0;
      d_maddr = ((RBASE + 4 * (k - 2)) & 4095) >> 2; d_mdata = pkt[k];
      edge_();
      d_wb = 0;
    end
    d_tx = 0; d_credit = 0;
  endtask

  initial begin
    repeat (3) edge_();
    reset = 0;
    repeat (2) edge_();
    // packet 1: TX header accepted at the first edge after send(); RX header 12 edges later
    build(18);
    fork
      send(3, 2, 5, 1);
      begin repeat (1 + 12) edge_(); recv(7, 6, 2); end
    join
    repeat (5) edge_();
    // packet 2: no block, gap or stall (the address comes before the size flit)
    build(5);
    d_raddr = RBASE; d_rcmd = ~d_rcmd;
    fork
      send(-1, 0, -1, 0);
      begin repeat (1 + 12) edge_(); recv(0, -1, 0); end
    join
    repeat (5) edge_();
    $finish;
  end
endmodule
