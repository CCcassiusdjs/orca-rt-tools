package orca_pkg;

`include "orca_defs.svh"

typedef logic[`BUS_WIDTH-1:0] word_t;
typedef logic[(`BUS_WIDTH >> 1)-1:0] hword_t;
typedef logic[(`BUS_WIDTH << 1)-1:0] dword_t;

const byte BLUE      = "\033[94m";
const byte CYAN      = "\033[96m";
const byte GREEN     = "\033[92m";
const byte YELLOW    = "\033[93m";
const byte RED       = "\033[91m";
const byte BOLD      = "\033[1m";
const byte UNDERLINE = "\033[4m";
const byte HEADER    = "\033[95m";
const byte ENDL      = "\033[0m";

// reverse byte order
function word_t endianess(word_t data);
  endianess = { data[7:0], data[15:8], data[23:16], data[31:24] };
endfunction

endpackage