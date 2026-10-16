module core_rv32e #(parameter MEMORY_WIDTH = 32) (
  input logic clock,
  input logic reset,
  interface_core_rv32e.CPU cpu_if
);

  // bind routercc (vhdl) to router_if
  processor processor(
    .clk_i(cpu_if.clock), 
    .rst_i(cpu_if.reset),

    .stall_i(cpu_if.stall_in),

    .addr_o(cpu_if.addr_out),
    .data_w_o(cpu_if.wb_out),

    .data_mode_o(cpu_if.data_mode_out),

    .extio_in(cpu_if.extio_in),
    .extio_out(cpu_if.extio_out),

    .data_i(cpu_if.data_in),
    .data_o(cpu_if.data_out)
  );

endmodule: core_rv32e
