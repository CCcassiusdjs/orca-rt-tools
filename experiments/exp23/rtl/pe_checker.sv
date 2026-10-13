// Packet integrity monitor of the PE (simulation only; does not change the
// RTL). chk_binds.sv binds it to each manycore_pe. It uses only interface
// signals of the DDMA, common to the original (4c299fc) and fixed versions.
//
// Send: on the rising edge of send_cmd_in, copies [destination, size,
// payload] from memory (memory_mod.mem) and compares it with the flits the
// router accepts (rx = 1 and credit_o = 1 at the clock edge).
// Receive: each payload flit the router releases (tx = 1 and credit_i = 1)
// produces an expected write (base address + 4k, data); each DDMA write on
// port A (wb_in != 0) consumes the next expected write. A write without a
// matching flit counts as spurious.
//
// Flit times (one line per packet and side, printed when the last flit
// passes; cycle = rising edges of the clock since time 0, common to all
// PEs; t = $time in ns):
//   FLIT TX t=<t of the header> src=<x-y> dst=<x-y> tag=<n> size=<p>
//           head=<cycle> last=<cycle> block=<n> gap=<n>
//   FLIT RX t=<t of the last flit> src=<x-y> dst=<x-y> tag=<n> size=<p>
//           head=<cycle> last=<cycle> stall=<n> gap=<n>
// TX (LOCAL input port of the source router, flits of the DDMA): head =
// edge where the router accepts the header (rx = 1, credit_o = 1), last =
// edge where it accepts the last flit; between them, block = edges with
// rx = 1 and credit_o = 0, gap = edges with rx = 0. RX (LOCAL output port
// of the destination router, flits to the DDMA): head = first edge with
// the header on data_o (tx = 1), last = edge where the DDMA takes the last
// flit (tx = 1, credit_i = 1); between them, inclusive, stall = edges with
// tx = 1 and credit_i = 0, gap = edges with tx = 0. size = size flit
// (payload flits p). TX.head and RX.last are the two points of the
// zero-load testbench (experiments/zll), where RX.last - TX.head =
// 6(m+1) + p + 1; there, RX.head - TX.head = 6(m+1). Counting the edges of
// the RX window gives RX.last - RX.head = p + 1 + stall + gap.
// Labels x-y follow ADDRESS (X[15:8], Y[7:0]), as the CHKSUM lines and the
// `scheduled` and TAG lines of manycore_pe.sv. dst of TX comes from the
// header flit; src of RX from source_node (noc_packet_t word 0) as
// id = y * DIMX + x; tag from noc_packet_t word 2. The core stores byte 0
// of a word in bits 31:24 (core_rv32e/datapath.vhd, store half word): the
// field at byte offset 0 of a word is {w[23:16], w[31:24]} and the field
// at offset 2 is {w[7:0], w[15:8]}.
module pe_checker #(parameter int ADDRESS = 0, parameter int RAM_MSIZE = 65536) (
  input logic        clock,
  input logic        reset,
  input logic        rx,
  input logic        credit_o,
  input logic [31:0] data_i,
  input logic        tx,
  input logic        credit_i,
  input logic [31:0] data_o,
  input logic        send_cmd_in,
  input logic [31:0] send_dest_in,
  input logic [31:0] send_addr_in,
  input logic [31:0] send_size_in,
  input logic [31:0] recv_addr_in,
  input logic        recv_cmd_in,
  input logic [3:0]  wb_in,
  input logic [31:0] mem_addr_in,
  input logic [31:0] mem_data_in
);
  timeunit 1ns;
  timeprecision 100ps;
  localparam int MAXERR = 20;
  int unsigned x = (ADDRESS >> 8) & 'hFF;
  int unsigned y = ADDRESS & 'hFF;

  // ---------------- send ----------------
  logic        prev_cmd = 0;
  bit          s_active = 0;
  int unsigned s_k, s_size, s_pkts = 0, s_ok = 0, s_err = 0, s_incomplete = 0;
  logic [31:0] s_exp [$];
  bit          s_bad;

  // ---------------- receive ----------------
  int unsigned r_k = 0, r_size = 0, r_pkts = 0, r_flits = 0;
  int unsigned r_err = 0, r_spurious = 0, r_missing = 0;
  logic [31:0] r_base = 0;
  bit          r_wait_base = 0;
  logic        prev_rcmd = 0;
  typedef struct { logic [31:0] widx; logic [31:0] data; } wr_t;
  wr_t         r_expq [$];

  function automatic logic [31:0] widx(input logic [31:0] a);
    return (a & (RAM_MSIZE - 1)) >> 2;
  endfunction

  // ---------------- flit times ----------------
  longint unsigned cyc = 0;
  int unsigned dimx = (ADDRESS >> 24) & 'hFF;
  bit              ft_on = 0;            // TX window open (header accepted)
  longint unsigned ft_head;
  longint          ft_t;
  int unsigned     ft_block, ft_gap;
  bit              fr_on = 0;            // RX window open (header on data_o)
  longint unsigned fr_head;
  int unsigned     fr_stall, fr_gap;
  logic [31:0]     fr_w0 = 0, fr_w2 = 0;

  // noc_packet_t fields (see the header of this file)
  function automatic int unsigned field_at0(input logic [31:0] w);
    return 32'({w[23:16], w[31:24]});
  endfunction
  function automatic int unsigned field_at2(input logic [31:0] w);
    return 32'({w[7:0], w[15:8]});
  endfunction

  always @(posedge clock) begin
    cyc++;
    if (!reset) begin
      // ---- send: new command ----
      if (send_cmd_in && !prev_cmd) begin
        if (s_active) begin
          s_incomplete++;
          if (s_err + s_incomplete <= MAXERR)
            $display("CHK %0t node %0d-%0d SEND incomplete: %0d of %0d flits", $time, x, y, s_k, s_size + 2);
        end
        s_exp.delete();
        s_exp.push_back(send_dest_in);
        s_exp.push_back(send_size_in);
        for (int i = 0; i < send_size_in; i++)
          s_exp.push_back(memory_mod.mem[widx(send_addr_in) + i]);
        s_size = send_size_in; s_k = 0; s_bad = 0; s_active = 1; s_pkts++;
      end
      prev_cmd <= send_cmd_in;

      // ---- send: flit times (window from the header to the last flit) ----
      if (ft_on && !(rx && credit_o)) begin
        if (rx) ft_block++; else ft_gap++;
      end

      // ---- send: flit accepted by the router ----
      if (rx && credit_o) begin
        if (s_active && s_k == 0) begin
          ft_on = 1; ft_head = cyc; ft_t = $time; ft_block = 0; ft_gap = 0;
        end
        if (!s_active) begin
          s_err++;
          if (s_err <= MAXERR) $display("CHK %0t node %0d-%0d SEND flit %h outside a packet", $time, x, y, data_i);
        end else begin
          if (s_k >= s_exp.size() || data_i !== s_exp[s_k]) begin
            if (!s_bad && s_err < MAXERR)
              $display("CHK %0t node %0d-%0d SEND flit %0d = %h, expected %h", $time, x, y, s_k, data_i,
                       (s_k < s_exp.size()) ? s_exp[s_k] : 32'hx);
            if (!s_bad) s_err++;
            s_bad = 1;
          end
          s_k++;
          if (s_k == s_size + 2) begin
            if (!s_bad) s_ok++;
            s_active = 0;
            if (ft_on)
              $display("FLIT TX t=%0d src=%0d-%0d dst=%0d-%0d tag=%0d size=%0d head=%0d last=%0d block=%0d gap=%0d",
                       ft_t, x, y, (s_exp[0] >> 8) & 'hFF, s_exp[0] & 'hFF,
                       (s_size >= 3) ? field_at2(s_exp[4]) : 0, s_size, ft_head, cyc, ft_block, ft_gap);
            ft_on = 0;
          end
        end
      end

      // ---- receive: flit times (window from the header to the last flit) ----
      if (tx && r_k == 0 && !fr_on) begin
        fr_on = 1; fr_head = cyc; fr_stall = 0; fr_gap = 0; fr_w0 = 0; fr_w2 = 0;
      end
      if (fr_on && !(tx && credit_i)) begin
        if (tx) fr_stall++; else fr_gap++;
      end

      // ---- receive: flit released by the router ----
      if (tx && credit_i) begin
        r_flits++;
        if (r_k == 1) begin
          r_size = data_o; r_wait_base = 1;
        end else if (r_k >= 2) begin
          automatic wr_t w; w.widx = widx(r_base + 4 * (r_k - 2)); w.data = data_o;
          r_expq.push_back(w);
          if (r_k == 2) fr_w0 = data_o;
          if (r_k == 4) fr_w2 = data_o;
        end
        r_k++;
        if (r_k >= 2 && r_k == r_size + 2) begin
          r_k = 0; r_pkts++;
          if (fr_on) begin
            automatic int unsigned sid = field_at0(fr_w0);
            $display("FLIT RX t=%0d src=%0d-%0d dst=%0d-%0d tag=%0d size=%0d head=%0d last=%0d stall=%0d gap=%0d",
                     $time, (dimx != 0) ? sid % dimx : sid, (dimx != 0) ? sid / dimx : 0, x, y,
                     (r_size >= 3) ? field_at2(fr_w2) : 0, r_size, fr_head, cyc, fr_stall, fr_gap);
          end
          fr_on = 0;
        end
      end

      // ---- receive: address given by the CPU ----
      if (recv_cmd_in != prev_rcmd && r_wait_base) begin
        r_base = recv_addr_in; r_wait_base = 0;
      end
      prev_rcmd <= recv_cmd_in;

      // ---- receive: DDMA write to memory ----
      if (wb_in != 0) begin
        if (r_expq.size() == 0) begin
          r_spurious++;
          if (r_err + r_spurious <= MAXERR)
            $display("CHK %0t node %0d-%0d RECV spurious write word %0d = %h", $time, x, y, mem_addr_in, mem_data_in);
        end else begin
          automatic wr_t e = r_expq.pop_front();
          if (e.widx !== mem_addr_in || e.data !== mem_data_in) begin
            r_err++;
            if (r_err + r_spurious <= MAXERR)
              $display("CHK %0t node %0d-%0d RECV write word %0d = %h, expected word %0d = %h", $time, x, y,
                       mem_addr_in, mem_data_in, e.widx, e.data);
          end
        end
      end
    end
  end

  final begin
    r_missing = r_expq.size();
    $display("CHKSUM node %0d-%0d send_pkts=%0d send_ok=%0d send_err=%0d send_incomplete=%0d recv_pkts=%0d recv_flits=%0d recv_err=%0d recv_spurious=%0d recv_missing=%0d",
             x, y, s_pkts, s_ok, s_err, s_incomplete, r_pkts, r_flits, r_err, r_spurious, r_missing);
  end
endmodule
