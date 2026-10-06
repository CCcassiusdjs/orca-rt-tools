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

  always @(posedge clock) begin
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

      // ---- send: flit accepted by the router ----
      if (rx && credit_o) begin
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
          end
        end
      end

      // ---- receive: flit released by the router ----
      if (tx && credit_i) begin
        r_flits++;
        if (r_k == 1) begin
          r_size = data_o; r_wait_base = 1;
        end else if (r_k >= 2) begin
          automatic wr_t w; w.widx = widx(r_base + 4 * (r_k - 2)); w.data = data_o;
          r_expq.push_back(w);
        end
        r_k++;
        if (r_k >= 2 && r_k == r_size + 2) begin r_k = 0; r_pkts++; end
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
