module peripherals #(parameter MEMORY_BUS_WIDTH = 32)
(interface_peripherals.PERIPHERALS pheripherals_if);

  peripherals_minimal periph_mod (
    .clk_i(pheripherals_if.clock),
		.rst_i(pheripherals_if.reset),
		.addr_i(pheripherals_if.addr_in),
		.data_i(pheripherals_if.data_in),
		.data_o(pheripherals_if.data_out),
		.sel_i(pheripherals_if.sel_in),
		.wr_i(pheripherals_if.wr_in),
		.irq_o(pheripherals_if.irq),
		.gpioa_in(pheripherals_if.gpioa_in),
		.gpioa_out(pheripherals_if.gpioa_out),
		.gpioa_ddr(pheripherals_if.gpioa_ddr)
  );

endmodule: peripherals