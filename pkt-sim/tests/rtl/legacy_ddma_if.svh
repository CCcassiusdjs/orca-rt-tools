// DDMA interface from 2023-03 (commit 40adeeb), used by hw/tcd/tcd.sv.
// Only for tb_tcd; the current version of interface_ddma lacks these signals.
interface interface_ddma (input clock, input reset);
  logic [31:0] addr_in;
  logic [31:0] nbytes_in;
  logic cmd_in;
  logic [31:0] status_out;
  modport TCD (input clock, reset, status_out, output addr_in, nbytes_in, cmd_in);
endinterface
