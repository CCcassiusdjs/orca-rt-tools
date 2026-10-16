`define BUS_WIDTH 32

`define COLORS

`ifdef COLORS

  `define info(A) \
    $write("%0s", GREEN); \
    $write("%0s", $sformatf A); \
    $write("%0s\n", ENDL)

  `define warn(A) \
    $write("%0s", YELLOW); \
    $write("%0s", $sformatf A); \
    $write("%0s\n", ENDL)

  // the Verilator simulator reserves the `error directive; the active code
  // does not use this macro
  `ifndef VERILATOR
  `define error(A) \
    $write("%0s", RED); \
    $write("%0s", $sformatf A); \
    $write("%0s\n", ENDL)
  `endif

  `define notice(A) \
    $write("%0s", CYAN); \
    $write("%0s", $sformatf A); \
    $write("%0s\n", ENDL)

  `define debug(A) \
    $write("%0s", BLUE); \
    $write("%0s", $sformatf A); \
    $write("%0s\n", ENDL)

  `define link(A) \
    $write("%0s", UNDERLINE); \
    $write("%0s", $sformatf A); \
    $write("%0s\n", ENDL)

  `define bold(A) \
    $write("%0s", BOLD); \
    $write("%0s", $sformatf A); \
    $write("%0s\n", ENDL)

  `define header(A) \
    $write("%0s", HEADER); \
    $write("%0s", $sformatf A); \
    $write("%0s\n", ENDL)

`else
  `define info(A) $display("%0s", $sformatf A)
  `define warn(A) $display("%0s", $sformatf A)
  `ifndef VERILATOR
  `define error(A) $display("%0s", $sformatf A)
  `endif
  `define notice(A) $display("%0s", $sformatf A)
  `define debug(A) $display("%0s", $sformatf A)
  `define link(A) $display("%0s", $sformatf A)
  `define bold(A) $display("%0s", $sformatf A)
  `define header(A) $display("%0s", $sformatf A)
`endif