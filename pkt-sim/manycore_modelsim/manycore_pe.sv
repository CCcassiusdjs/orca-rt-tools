// Explicit time unit: $time counts ns. Without this directive (commit
// 4c299fc), the simulator assigned the 100 ps unit to this module, and the
// logs (scheduled, TAG, TRIGGER) came out in tenths of ns. Precision 1 fs,
// as manycore_top.sv (clock half period in fs).
`timescale 1ns/1fs

import orca_pkg::*;

module manycore_pe #(parameter
  MEMORY_WIDTH,
  FLIT_WIDTH,
  RAM_MSIZE,
  BOOT_MSIZE,               /* INTENTIONALLY LEFT NO DEFAULT VALUES */
  ADDRESS,
  INTERLEAVING_GRAIN,
  NOC_DIM_X,
  NOC_DIM_Y,
  // clock and release of the source task (manycore_top.sv); the
  // defaults are the values of run F (500 MHz, T = 0.5 ms, 3 ms warm-up)
  longint CLOCK_HALF_PERIOD_FS = 1_000_000,
  longint RELEASE_CYCLES = 250_000,
  longint WARMUP_CYCLES = 1_500_000,
  // release generator (manycore_top.sv): bit k enables the generator of the
  // PE with node index k = y * NOC_DIM_X + x; default: PE 0, application E
  parameter logic [63:0] RELEASE_MASK = 64'd1
)(
  input logic clock,
  input logic reset,
  interface_pe.PE pe_if
);


  // =========================================================
  //                    memory "map"
  // =========================================================
  const int BOOT_START        = 'h00000000;  const int BOOT_END        = 'h1fffffff;
  const int RAM_START         = 'h40000000;  const int RAM_END         = 'h5fffffff;
  const int PERIPH_START      = 'he1000000;  const int PERIPH_END      = 'hefffffff;
  const int INTERNAL_START    = 'hf0000000;  const int INTERNAL_END    = 'hffffffff;
  const int DDMA_CONFIG_START = 'h20000000;  const int DDMA_CONFIG_END = 'h2000004C;
  const int PRINTCHAR_ADDR    = 'hf00000d0;  


  // ADDRESS = DIMX[31:24] | DIMY[23:16] | X[15:8] | Y[7:0] (manycore_top.sv)
  function int addr_x();
    addr_x = (ADDRESS >> 8) & 'h00FF;
  endfunction

  function int addr_y();
    addr_y = ADDRESS & 'h00FF;
  endfunction

  function string log_filename();
    automatic string sx;
    automatic string sy;
    automatic int x;
    automatic int y;

    x = addr_x();
    y = addr_y();

    sx.itoa(x);
    sy.itoa(y);

    log_filename = {"../logs/output-", sx, "-", sy, ".txt"};
  endfunction

  int print_file = $fopen(log_filename());
  
  // =========================================================
  //                    INTERFACES
  // =========================================================
  interface_router #(FLIT_WIDTH) router_if(clock, reset); // router and pe
  interface_router_port #(FLIT_WIDTH) router_port_if(clock, reset); // router and ddma
  interface_ddma   #(MEMORY_WIDTH, FLIT_WIDTH, INTERLEAVING_GRAIN, ADDRESS) ddma_if(clock, reset); //tcd and ddma
  
  interface_memory #(MEMORY_WIDTH) mem_if_dma(clock, reset); // mem and ddma
  interface_memory #(MEMORY_WIDTH) mem_if_mmio(clock, reset); // mem and mmio
  interface_memory #(MEMORY_WIDTH) mem_if_boot(clock, reset); // boot rom

  interface_peripherals #(MEMORY_WIDTH) perif_if(clock, reset);
  interface_core_rv32e  #(MEMORY_WIDTH) cpu_if(clock, reset); // cpu to mmio
  interface_tcd    #(MEMORY_WIDTH) tcd_if(clock, reset);
  

  // =========================================================
  //                    MODULES
  // =========================================================
  peripherals #(MEMORY_WIDTH) perif_mod(
    .pheripherals_if(perif_if.PERIPHERALS)
  );

  // RAM size is expressed in words (32-bit). We convert from
  // bytes to word by dividing RAM_MSIZE by 4, also adding
  // 1 to the result to preventing the last half word to be missing
  dual_port_ram #(MEMORY_WIDTH, (RAM_MSIZE >> 2) +1) memory_mod(
    .clock(clock), .reset(reset), .enable(1'b1),
    .mem_if_a(mem_if_dma.MEM),
    .mem_if_b(mem_if_mmio.MEM)
  );

  single_port_ram #(MEMORY_WIDTH, (BOOT_MSIZE >> 2) +1) boot_mod(
    .clock(clock), .reset(reset), .enable(1'b1),
    .mem_if_a(mem_if_boot.MEM)
  );

  ddma #(MEMORY_WIDTH, FLIT_WIDTH, INTERLEAVING_GRAIN, 
    ADDRESS, RAM_MSIZE
  ) ddma_mod(
    .clock(clock), .reset(reset), 
    .router_if(router_port_if.DDMA),
    .mem_if(mem_if_dma.DUT),
    .ddma_if(ddma_if.DDMA)
  );

  router #(ADDRESS) router_mod (
    .clock(clock), .reset(reset),
    .router_if(router_if.ROUTER)
  );

  core_rv32e #(MEMORY_WIDTH) cpu_mod (
    .clock(clock), .reset(reset),
    .cpu_if(cpu_if.CPU)
  );


  // =========================================================
  //                    MMIO REGISTERS
  // =========================================================
  word_t ddma_send_dest_in;
  word_t ddma_send_addr_in;
  word_t ddma_send_size_in;
  logic ddma_send_cmd_in;
  word_t ddma_recv_addr_in;
  logic ddma_recv_cmd_in;


  word_t cacc_reg;
  word_t cacc_counter;    // log time
  word_t cacc_counter_2;  // log sched
  word_t cacc_counter_3;  // log send ops
  word_t cacc_counter_4;  // log recv ops
  word_t cacc_iter;       // log iteration markers (device/cacc.h, ITER_BEGIN/ITER_END)

  // written word in the byte order of the registers; the iteration marker
  // prints its fields: bit 31 end/begin, bits 30:24 task letter, 23:0 k
  word_t cpu_wdata;
  assign cpu_wdata = endianess(cpu_if.data_out);


  always_comb begin
    ddma_if.send_dest_in = ddma_send_dest_in;
    ddma_if.send_addr_in = ddma_send_addr_in;
    ddma_if.send_size_in = ddma_send_size_in;
    ddma_if.send_cmd_in = ddma_send_cmd_in;

    ddma_if.recv_addr_in = ddma_recv_addr_in;
    ddma_if.recv_cmd_in = ddma_recv_cmd_in;
  end 

  typedef enum logic[1:0] {
    COUNTING = 2'b01,
    IRQ_SEND = 2'b10,
    INC_EPOCH = 2'b11
  } wake_up_state_s;

  // workflow controller, mimics external comm system. The release of A
  // is due at cycle WARMUP_CYCLES + k RELEASE_CYCLES (k = 0, 1, ...) and
  // the controller sees it at the rising edge of that cycle. The count of
  // cycles keeps the release period at T F_CLK cycles at any clock; the
  // tick of the kernel also counts cycles (F_CPU / F_TIMER, hal.c). At
  // 500 MHz it fires at the same edges as the former test
  // $time >= 3_000_000 + k 500_000 ns (rising edge n at 2 n + 1 ns).
  logic   wake_up_irq;
  longint wake_up_cycle = 0;        // rising edges of clock before the current one
  longint wake_up_counter_next;     // cycle of the next release
  wake_up_state_s wake_up_state;

  // start of cycle c in ns (truncated), for the TRIGGER line
  function automatic longint cycle_ns(input longint c);
    return (c * 2 * CLOCK_HALF_PERIOD_FS) / 1_000_000;
  endfunction

  always @(posedge clock) wake_up_cycle <= wake_up_cycle + 1;
  
  logic wakeup_ack_flip; // written by memory
  logic wakeup_ack_flip_sh; // written by process

  // node index of this PE (software numbering, device/ddma.c) and the
  // generators: RELEASE_HERE enables the generator of this PE; the PE with
  // the lowest enabled index (RELEASE_FIRST) prints the TRIGGER lines of
  // application E, which the analysis reads as the release of an
  // iteration; every other enabled PE prints "TRIGGER-PE" lines.
  localparam int NODE_INDEX = (ADDRESS & 'hFF) * NOC_DIM_X + ((ADDRESS >> 8) & 'hFF);
  localparam logic [63:0] RELEASE_LOWEST = RELEASE_MASK & (~RELEASE_MASK + 64'd1);
  localparam bit RELEASE_HERE = RELEASE_MASK[NODE_INDEX];
  localparam bit RELEASE_FIRST = RELEASE_HERE && RELEASE_LOWEST == (64'd1 << NODE_INDEX);

  always @(posedge clock) begin
    if (~reset && RELEASE_HERE) begin

      // $display(ADDRESS, ADDRESS & 'h0000FFFF);
        
      case (wake_up_state)
        COUNTING: begin
          wake_up_counter_next <= wake_up_counter_next;
          wake_up_state <= (wake_up_cycle >= wake_up_counter_next) ? IRQ_SEND : COUNTING;
          wake_up_irq <= 0;
        end

        IRQ_SEND: begin
          wake_up_counter_next <= wake_up_counter_next;
          if (wakeup_ack_flip != wakeup_ack_flip_sh) begin
            wake_up_state <= INC_EPOCH;
            if (RELEASE_FIRST) begin
              $display("TRIGGER: workflow iteration at %0d ns.", $time);
              $display("TRIGGER: next release will be at %0d ns",  cycle_ns(wake_up_counter_next + RELEASE_CYCLES));
            end else begin
              $display("TRIGGER-PE %0d-%0d: release acknowledged at %0d ns", addr_x(), addr_y(), $time);
            end
          end else begin
            wake_up_state <= IRQ_SEND;
          end
          wake_up_irq <= 1;
        end

        INC_EPOCH: begin
          wake_up_counter_next <= wake_up_counter_next + RELEASE_CYCLES;
          wake_up_state <= COUNTING;
          wake_up_irq <= 0;
        end

      endcase
  
      wakeup_ack_flip_sh <= wakeup_ack_flip;
      
    end else begin
      wake_up_state <= COUNTING;
      wake_up_counter_next <= WARMUP_CYCLES;
      wake_up_irq <= 0;
    end
  end 


  // =========================================================
  //                    MEM / CPU / PERIPHERALS
  // =========================================================
  // IRQ_IN is 00000RSP
  // R: ddma receive process irq
  // S: ddma send process ack irq
  // P: peripherals interruptions
  assign cpu_if.extio_in = { 3'b0,
    wake_up_irq,
    ddma_if.irq_recv_hshk_out, // irq 3
    ddma_if.irq_recv_size_out, // irq 2
    ddma_if.irq_send_out, 
    perif_if.irq };

  assign cpu_if.stall_in = 0;

  // memory output delay 
  word_t dly_address;
  always @(posedge clock) begin
    dly_address <= cpu_if.addr_out;
  end

  word_t a_dly_address; // aligned 4-byte delayed address
  assign a_dly_address = dly_address & ~3;

  // print interruptions 
  // always @(posedge clock) begin 
  //   if (cpu_if.extio_in != $past(cpu_if.extio_in)) begin
  //     $display("[%0d ns] Node 0x%h Irq %b", ($time/1000), ADDRESS & 'h0000FFFF, cpu_if.extio_in); 
  //   end 
  // end

  // printchar output
  always @(posedge clock) begin 
    if (dly_address == PRINTCHAR_ADDR && print_file != 0) begin
      $fwrite(print_file, "%c", cpu_if.data_out[31:24]);
    end
  end

  // registered memory access to cpu.data_in
  always_comb begin
    cpu_if.data_in = 0; // default: no latch

    // boot mem
    if (dly_address >= BOOT_START && dly_address <= BOOT_END) begin
      cpu_if.data_in = mem_if_boot.data_out;

    // ram mem
    end else if (dly_address >= RAM_START && dly_address <= RAM_END) begin
      cpu_if.data_in = mem_if_mmio.data_out;
    
    // peripherals
    end else if (dly_address >= PERIPH_START && dly_address <= PERIPH_END) begin 
      cpu_if.data_in = endianess(perif_if.data_out);

    // internals (e.g., interruption controller)
    end else if (dly_address >= INTERNAL_START && dly_address <= INTERNAL_END) begin
      cpu_if.data_in = 0; 

    // ddma config zone
    end else if (dly_address >= DDMA_CONFIG_START && dly_address <= DDMA_CONFIG_END) begin

      case (a_dly_address)
        'h20000000: cpu_if.data_in = endianess(ADDRESS);
        'h20000004: cpu_if.data_in = endianess(ddma_if.send_dest_in[7:0]);
        'h20000008: cpu_if.data_in = endianess(ddma_if.send_addr_in);
        'h2000000C: cpu_if.data_in = endianess(ddma_if.send_size_in);
        'h20000010: cpu_if.data_in = endianess(ddma_if.send_cmd_in);
        'h20000014: cpu_if.data_in = endianess({ 16'b0,
                                                  ddma_if.state_send_out,
                                                  ddma_if.state_recv_out
                                                });
        'h20000018: cpu_if.data_in = endianess(ddma_if.recv_addr_in);
        'h2000001C: cpu_if.data_in = endianess(ddma_if.recv_addr_out);
        'h20000020: cpu_if.data_in = endianess(ddma_if.recv_size_out);
        'h20000024: cpu_if.data_in = endianess(ddma_if.recv_cmd_in);
        'h20000028: cpu_if.data_in = endianess(cacc_reg);
        'h2000002C: cpu_if.data_in = endianess(cacc_counter);
        'h20000030: cpu_if.data_in = endianess(cacc_counter_2);
        'h20000034: cpu_if.data_in = endianess(cacc_counter_3);
        'h20000038: cpu_if.data_in = endianess(cacc_counter_4);
        'h2000003C: cpu_if.data_in = endianess(cacc_iter);
        'h2000004C: cpu_if.data_in = endianess(wakeup_ack_flip);
        default: begin
            $display("[%0d ns] illegal read to ddma %h %h.", ($time), 
              dly_address, a_dly_address);
        end 
      endcase

    // unknown addressess
    end else if ($time() != 0 && dly_address != PRINTCHAR_ADDR) begin
      $display("[%0d ns] illegal read to region %h.", ($time), dly_address);
      cpu_if.data_in = 0;
    end 
  end 

  // BOOT memory mux
  always_comb begin
    mem_if_boot.data_in = 0; // boot is ready only
    mem_if_boot.wb_in = 0;   // boot is ready only

    if (cpu_if.addr_out >= BOOT_START && cpu_if.addr_out <= BOOT_END) begin
      mem_if_boot.addr_in = (cpu_if.addr_out & (BOOT_MSIZE -1)) >> 2;
    end else begin 
      mem_if_boot.addr_in = 0;
    end
  end
  
  // RAM memory mux
  always_comb begin
    mem_if_mmio.data_in = cpu_if.data_out;
    
    if (cpu_if.addr_out >= RAM_START && cpu_if.addr_out <= RAM_END) begin
      mem_if_mmio.addr_in = (cpu_if.addr_out & (RAM_MSIZE -1)) >> 2;
      mem_if_mmio.wb_in = cpu_if.wb_out;
    end else begin
      mem_if_mmio.addr_in = 0;
      mem_if_mmio.wb_in = 0;
    end 
  end

  // aligned cpu.addr_out to 4-byte word, prevent 
  // addressing from missing MMIO access
  word_t a_cpu_addr_out;
  assign a_cpu_addr_out = cpu_if.addr_out & ~3;

  always @(posedge clock) begin
    if(~reset) begin
      wakeup_ack_flip <= (a_cpu_addr_out == 'h2000004C && cpu_if.wb_out) ? endianess(cpu_if.data_out) : wakeup_ack_flip;
    end else begin
      wakeup_ack_flip <= 0;
    end
  end


  // cacc reg writing 
  always @(posedge clock) begin
    if(~reset) begin
      cacc_reg <= (a_cpu_addr_out == 'h20000028 && cpu_if.wb_out) ? endianess(cpu_if.data_out) : cacc_reg;
      cacc_counter <= (a_cpu_addr_out == 'h2000002C && cpu_if.wb_out) ? endianess(cpu_if.data_out) : cacc_counter + 1;
      cacc_counter_2 <= (a_cpu_addr_out == 'h20000030 && cpu_if.wb_out) ? endianess(cpu_if.data_out) : cacc_counter_2;
      cacc_counter_3 <= (a_cpu_addr_out == 'h20000034 && cpu_if.wb_out) ? endianess(cpu_if.data_out) : cacc_counter_3;
      cacc_counter_4 <= (a_cpu_addr_out == 'h20000038 && cpu_if.wb_out) ? endianess(cpu_if.data_out) : cacc_counter_4;
      cacc_iter <= (a_cpu_addr_out == 'h2000003C && cpu_if.wb_out) ? cpu_wdata : cacc_iter;

      if(a_cpu_addr_out == 'h20000038 && cpu_if.wb_out) begin
        $display("%0d %0d-%0d <- TAG %0d", $time, addr_x(), addr_y(), endianess(cpu_if.data_out));
      end

      if(a_cpu_addr_out == 'h20000034 && cpu_if.wb_out) begin
        $display("%0d %0d-%0d -> TAG %0d", $time, addr_x(), addr_y(), endianess(cpu_if.data_out));
      end

      if(a_cpu_addr_out == 'h20000030 && cpu_if.wb_out) begin
        $display("%0d %0d-%0d scheduled %0d", $time, addr_x(), addr_y(), endianess(cpu_if.data_out));
      end

      // one $display per kind: a ?: of "end" and "begin" pads "end" to 5 chars
      if(a_cpu_addr_out == 'h2000003C && cpu_if.wb_out && cpu_wdata[31]) begin
        $display("%0d %0d-%0d ITER end %c %0d", $time, addr_x(), addr_y(), {1'b0, cpu_wdata[30:24]}, cpu_wdata[23:0]);
      end

      if(a_cpu_addr_out == 'h2000003C && cpu_if.wb_out && !cpu_wdata[31]) begin
        $display("%0d %0d-%0d ITER begin %c %0d", $time, addr_x(), addr_y(), {1'b0, cpu_wdata[30:24]}, cpu_wdata[23:0]);
      end

    end else begin
      cacc_reg <= 0;
      cacc_counter <= 0;
      cacc_counter_2 <= 0;
      cacc_counter_3 <= 0;
      cacc_counter_4 <= 0;
      cacc_iter <= 0;
    end
  end 

  // data write to DDMA interface
  always @(posedge clock) begin
    if(~reset) begin 
      ddma_send_dest_in <= (a_cpu_addr_out == 'h20000004 && cpu_if.wb_out) ? endianess(cpu_if.data_out) : ddma_send_dest_in;
      ddma_send_addr_in <= (a_cpu_addr_out == 'h20000008 && cpu_if.wb_out) ? endianess(cpu_if.data_out) : ddma_send_addr_in;
      ddma_send_size_in <= (a_cpu_addr_out == 'h2000000C && cpu_if.wb_out) ? endianess(cpu_if.data_out) : ddma_send_size_in;
      ddma_send_cmd_in  <= (a_cpu_addr_out == 'h20000010 && cpu_if.wb_out) ? endianess(cpu_if.data_out) : ddma_send_cmd_in;
      ddma_recv_addr_in <= (a_cpu_addr_out == 'h20000018 && cpu_if.wb_out) ? endianess(cpu_if.data_out) : ddma_recv_addr_in;
      ddma_recv_cmd_in  <= (a_cpu_addr_out == 'h20000024 && cpu_if.wb_out) ? endianess(cpu_if.data_out) : ddma_recv_cmd_in;
    end else begin 
      ddma_send_dest_in <= 0;
      ddma_send_addr_in <= 0;
      ddma_send_size_in <= 0;
      ddma_send_cmd_in  <= 0;
      ddma_recv_addr_in <= 0;
      ddma_recv_cmd_in  <= 0;
    end
  end 
  
  // PERIPH mux
  always_comb begin
    perif_if.gpioa_in = 0;
    perif_if.data_in = endianess(cpu_if.data_out);

    if (cpu_if.addr_out >= PERIPH_START && cpu_if.addr_out <= PERIPH_END) begin
      perif_if.sel_in = 1;
      perif_if.addr_in = cpu_if.addr_out & ~3;
      perif_if.wr_in = cpu_if.wb_out;
    end else begin
      perif_if.sel_in = 0;
      perif_if.addr_in = 0;
      perif_if.wr_in = 0;
    end 
  end 

  // =========================================================
  //                    ROUTER CONNECTION
  // =========================================================
  always_comb begin
    // connect router inout to the pe (only S, N, W, and E ports)
    pe_if.clock_tx[3:0] = router_if.clock_tx[3:0];
    pe_if.tx[3:0] = router_if.tx[3:0];
    pe_if.data_o[3:0] = router_if.data_o[3:0];
    pe_if.credit_o[3:0] = router_if.credit_o[3:0];

    router_if.clock_rx[3:0] = pe_if.clock_rx[3:0];
    router_if.rx[3:0] = pe_if.rx[3:0];
    router_if.data_i[3:0] = pe_if.data_i[3:0];
    router_if.credit_i[3:0] = pe_if.credit_i[3:0];

    //connect router local port to the ddma (only L port)
    router_port_if.clock_tx = router_if.clock_tx[4];
    router_port_if.tx = router_if.tx[4];
    router_port_if.data_o = router_if.data_o[4];
    router_port_if.credit_o = router_if.credit_o[4];

    router_if.clock_rx[4] = router_port_if.clock_rx;
    router_if.rx[4] = router_port_if.rx;
    router_if.data_i[4] = router_port_if.data_i;
    router_if.credit_i[4] = router_port_if.credit_i;
  end

endmodule: manycore_pe
