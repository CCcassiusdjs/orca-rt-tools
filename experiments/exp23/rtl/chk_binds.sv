// precision 1 fs, as manycore_top.sv and manycore_pe.sv
`timescale 1ns/1fs
// Binds the monitor to each PE, prints the time units of manycore_top and
// manycore_pe ($printtimescale) and ends the simulation at +RUN_NS=<ns>
// (time of manycore_top).
module chk_binds;
  bind manycore_pe pe_checker #(.ADDRESS(ADDRESS), .RAM_MSIZE(RAM_MSIZE)) chk (
    .clock(clock), .reset(reset),
    .rx(router_port_if.rx), .credit_o(router_port_if.credit_o), .data_i(router_port_if.data_i),
    .tx(router_port_if.tx), .credit_i(router_port_if.credit_i), .data_o(router_port_if.data_o),
    .send_cmd_in(ddma_if.send_cmd_in), .send_dest_in(ddma_if.send_dest_in),
    .send_addr_in(ddma_if.send_addr_in), .send_size_in(ddma_if.send_size_in),
    .recv_addr_in(ddma_if.recv_addr_in), .recv_cmd_in(ddma_if.recv_cmd_in),
    .wb_in(mem_if_dma.wb_in), .mem_addr_in(mem_if_dma.addr_in), .mem_data_in(mem_if_dma.data_in)
  );

  longint run_ns;
  initial begin
    $display("timescale manycore_top:");
    $printtimescale(manycore_top);
    $display("timescale manycore_pe (0,0):");
    $printtimescale(manycore_top.pe_x[0].pe_y[0].pe_mod);
    if ($value$plusargs("RUN_NS=%d", run_ns)) begin
      #(run_ns * 1ns);
      $display("END at %0t (manycore_top time)", $realtime);
      $finish;
    end
  end
endmodule
