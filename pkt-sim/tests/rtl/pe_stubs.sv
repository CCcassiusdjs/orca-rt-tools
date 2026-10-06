// Stubs of the SystemVerilog wrappers that instantiate VHDL entities
// (router -> routercc, core_rv32e -> processor, peripherals ->
// peripherals_minimal). They allow elaborating manycore_pe.sv in Verilator.
// The "processor" is a bus master driven by the testbench
// through the tb_bus package.
package tb_bus;
  logic [31:0] addr = 0;
  logic [31:0] data = 0;
  logic [3:0]  wb   = 0;
endpackage

module router #(parameter ADDRESS = 0) (
  input logic clock,
  input logic reset,
  interface_router.ROUTER router_if
);
  assign router_if.clock_tx = {5{clock}};
  assign router_if.tx = 0;
  assign router_if.credit_o = 5'b11111;
  assign router_if.data_o = 0;
endmodule

module core_rv32e #(parameter MEMORY_WIDTH = 32) (
  input logic clock,
  input logic reset,
  interface_core_rv32e.CPU cpu_if
);
  assign cpu_if.addr_out = tb_bus::addr;
  assign cpu_if.data_out = tb_bus::data;
  assign cpu_if.wb_out = tb_bus::wb;
  assign cpu_if.data_mode_out = 0;
  assign cpu_if.extio_out = 0;
endmodule

module peripherals #(parameter MEMORY_BUS_WIDTH = 32)
(interface_peripherals.PERIPHERALS pheripherals_if);
  assign pheripherals_if.data_out = 0;
  assign pheripherals_if.irq = 0;
  assign pheripherals_if.gpioa_out = 0;
  assign pheripherals_if.gpioa_ddr = 0;
endmodule
