import orca_pkg::*;

`include "orca_defs.svh"

/**
 * This module is a double dma that can asyncronously sends and receive packets.
 * There is only one memory bus, which is shared between sending and receiving 
 * processes. Access to the port is given to one of the processess in a round-robin
 * fashion priority schema. The cpu must configure the DMA to send packets. The 
 * interruption wire raises when a packet is tranferred to the memory. */
module ddma #(parameter 
  MEMORY_BUS_WIDTH, 
  FLIT_WIDTH, 
  INTERLEAVING_GRAIN, 
  ADDRESS,
  RAM_MSIZE
)(
  input logic clock,
  input logic reset,

  interface_router_port.DDMA router_if,
  interface_memory.DUT mem_if,
  interface_ddma.DDMA ddma_if
);

  //==============================================================

  // interleaving_state_t represents the process which has priority in 
  // the interleaving system. 
  typedef enum logic[3:0] {
    TOKEN_SEND = 4'b0001,
    TOKEN_RECV = 4'b0010,
    TOKEN_SEND_TO_RECV = 4'b0100,
    TOKEN_RECV_TO_SEND = 4'b1000
  } interleaving_state_t;
  
  // send process state machine states 
  typedef enum logic[7:0] {
    SENDING_IDLE            = 8'b0000_0001,
    SENDING_HEADER          = 8'b0000_0010,
    SENDING_SIZE            = 8'b0000_0100,
    SENDING_PAYLOAD_DELAYER = 8'b0000_1000,
    SENDING_PAYLOAD         = 8'b0001_0000,
    SENDING_PAYLOAD_CLEANUP = 8'b0010_0000,
    SENDING_HANDSHAKE       = 8'b0100_0000
  } send_state_t;

  // recv process state machine states 
  typedef enum logic[7:0] {
    RECEIVING_HEADER        = 8'b0000_0001,
    RECEIVING_SIZE_DELAYER  = 8'b0000_0010,
    RECEIVING_SIZE          = 8'b0000_0100,    
    RECEIVING_IRQ_ADDR      = 8'b0000_1000,
    RECEIVING_PAYLOAD_DELAY = 8'b0001_0000,
    RECEIVING_PAYLOAD       = 8'b0010_0000,
    RECEIVING_HANDSHAKE     = 8'b0100_0000
  } recv_state_t;
  
  // token status (which process has priority, either send or recv)
  interleaving_state_t istate;

  // remaining cycles until interleaving priority switching  
  word_t i_flip_counter;

  // send/recv state variables 
  send_state_t sstate;
  recv_state_t rstate;

  // send regs
  word_t temp_addr_in;
  word_t temp_num_flits_in;
  word_t temp_destination;

  // recv regs
  word_t temp_flits_to_recv;
  word_t temp_recv_addr;
  
  // token request for recv and send states 
  logic has_data_to_send;
  logic has_data_to_recv;

  assign has_data_to_send = (sstate != SENDING_IDLE   && sstate != SENDING_HANDSHAKE);
  // recv flags (declared here, used by the interleaving request)
  logic recv_drop;          // current packet targets another node
  assign has_data_to_recv = (rstate == RECEIVING_PAYLOAD_DELAY || rstate == RECEIVING_PAYLOAD) && !recv_drop;

  // ============================== INTERLEAVING ============================
  // process for handling interleaving arbitration. 
  // rules:
  // - interleaving changes between sending and receiving actions
  // - an action changes if it timeouts or finish before the timeout
  // - if an action chaging would cause no effect, it won't change instead

  integer send_serial_counter = 0;

  // address can come from either send or receiving processess. 
  // memory will be set to write mode only when receiving flits,
  // otherwise it'll reside in read mode 
  // ** addr_in is 4-byte aligned
  // ** addr_in is capped to memory size
  always_comb begin
    if(istate == TOKEN_SEND || istate == TOKEN_RECV_TO_SEND) begin
      mem_if.addr_in = (temp_addr_in & (RAM_MSIZE -1)) >> 2;
    end else begin
      mem_if.addr_in = (temp_recv_addr & (RAM_MSIZE -1)) >> 2;
    end
  end

  always @(posedge clock) begin
    if(~reset) begin
      case (istate) 

        TOKEN_SEND: begin
          if (i_flip_counter == 1) begin
            if(has_data_to_recv) begin
              istate <= TOKEN_SEND_TO_RECV;
            end
          end else begin
            i_flip_counter <= i_flip_counter - 1;
          end
        end 

        TOKEN_RECV: begin
          if (i_flip_counter == 1) begin
            if(has_data_to_send) begin
              istate <= TOKEN_RECV_TO_SEND;
            end
          end else begin
            i_flip_counter <= i_flip_counter - 1;
          end
        end 

        TOKEN_SEND_TO_RECV: begin
          istate <= TOKEN_RECV;
          i_flip_counter <= INTERLEAVING_GRAIN;
        end

        TOKEN_RECV_TO_SEND: begin 
          istate <= TOKEN_SEND;
          i_flip_counter <= INTERLEAVING_GRAIN;
        end 
      endcase

    end else begin
      istate <= TOKEN_SEND; // default state
      i_flip_counter <= INTERLEAVING_GRAIN;
    end
  end 

  // ============================== SENDING ============================
  // Router handshake: the router accepts the flit presented on data_i at
  // the clock edge where rx = 1 and credit_o = 1. A presented flit stays
  // on data_i (rx = 1) until that edge; the state machine advances only
  // on acceptance. Payload words come from memory (1-cycle read latency)
  // through a 2-entry prefetch queue, so the port sends one flit per
  // cycle while credit holds and the memory token stays with the send
  // process. Without backpressure, the timing matches the previous
  // version: header accepted 2 cycles after send_cmd_in, size on the
  // next cycle, one idle cycle, then one payload flit per cycle.
  logic send_accept;
  assign send_accept = router_if.rx & router_if.credit_o;

  word_t send_fetch_left;   // payload words still to read from memory
  word_t send_flits_left;   // payload flits still to be accepted
  word_t send_q [0:1];      // prefetch queue
  logic [1:0] send_q_count;
  logic send_rd_inflight;   // read issued in the previous cycle

  always @(posedge clock) begin : SENDING
    automatic word_t q0, q1;
    automatic logic [1:0] qc;
    automatic logic take;

    if(~reset) begin
      // 1) word read in the previous cycle enters the queue
      q0 = send_q[0]; q1 = send_q[1]; qc = send_q_count;
      if (send_rd_inflight) begin
        if (qc == 0) q0 = mem_if.data_out; else q1 = mem_if.data_out;
        qc = qc + 1;
      end

      // 2) the address on the memory bus in this cycle counts as a read
      //    when the send process holds the token and the queue has room
      //    for the word (it arrives on the next edge)
      if ((sstate == SENDING_HEADER || sstate == SENDING_SIZE || sstate == SENDING_PAYLOAD)
          && send_fetch_left != 0 && istate == TOKEN_SEND && qc < 2) begin
        send_rd_inflight <= 1;
        temp_addr_in <= temp_addr_in + 4;
        send_fetch_left <= send_fetch_left - 1;
      end else begin
        send_rd_inflight <= 0;
      end

      // 3) router port
      take = 0;
      case (sstate)
        SENDING_IDLE: begin   // wait for sw configuration
          temp_addr_in <= ddma_if.send_addr_in;
          temp_num_flits_in <= ddma_if.send_size_in;
          temp_destination <= ddma_if.send_dest_in;
          send_fetch_left <= ddma_if.send_size_in;
          send_flits_left <= ddma_if.send_size_in;
          send_rd_inflight <= 0;
          qc = 0;
          router_if.rx <= 0;
          if (ddma_if.send_cmd_in == 1) sstate <= SENDING_HEADER;
        end

        SENDING_HEADER: begin  // present header flit until accepted
          if (send_accept) begin
            router_if.data_i <= temp_num_flits_in;
            router_if.rx <= 1;
            sstate <= SENDING_SIZE;
          end else begin
            router_if.data_i <= temp_destination;
            router_if.rx <= 1;
          end
        end

        SENDING_SIZE: begin  // present size flit until accepted
          if (send_accept) begin
            router_if.rx <= 0;
            sstate <= (send_flits_left == 0) ? SENDING_HANDSHAKE : SENDING_PAYLOAD;
          end
        end

        SENDING_PAYLOAD: begin // copy payload onto router port
          automatic word_t left;
          left = send_flits_left - (send_accept ? 1 : 0);
          send_flits_left <= left;
          if (!router_if.rx || send_accept) begin
            if (left == 0) begin
              router_if.rx <= 0;
              sstate <= SENDING_HANDSHAKE;
            end else if (qc != 0) begin
              router_if.data_i <= q0;
              router_if.rx <= 1;
              take = 1;
            end else begin
              router_if.rx <= 0;
            end
          end
        end

        SENDING_HANDSHAKE: begin
          router_if.rx <= 0;
          if(ddma_if.send_cmd_in == 0) begin
            sstate <= SENDING_IDLE;
          end
        end

        default: begin
          router_if.rx <= 0;
          sstate <= SENDING_IDLE;
        end
      endcase

      // 4) queue update
      if (take) begin
        send_q[0] <= q1;
        send_q_count <= qc - 1;
      end else begin
        send_q[0] <= q0;
        send_q[1] <= q1;
        send_q_count <= qc;
      end

    end else begin
      sstate <= SENDING_IDLE;
      router_if.rx <= 0;
      router_if.data_i <= 0;
      temp_addr_in <= 0;
      temp_num_flits_in <= 0;
      temp_destination <= 0;
      send_fetch_left <= 0;
      send_flits_left <= 0;
      send_q_count <= 0;
      send_rd_inflight <= 0;
    end
  end

  // ============================== RECEIVING ============================
  // The router releases the flit on data_o at the clock edge where tx = 1
  // and credit_i = 1. Header and size flits keep the previous timing
  // (registered credit). For the payload, credit_i and the memory write
  // enable are combinational and equal: a flit is written exactly when
  // the router releases it, and only while the receive process holds
  // the memory token. Address and flit count advance on that event.
  // The previous version granted credit one cycle ahead and rewound the
  // address on every cycle without a flit; while the send process held
  // the token, the address moved back up to INTERLEAVING_GRAIN words, and
  // a write could reach the send address during the token switch.
  //
  // Destination check: a header whose XY field (bits 15:0) differs from
  // ADDRESS[15:0] marks the packet as foreign; the DDMA consumes its
  // flits without writing memory and without interrupting the CPU, and
  // increments recv_drop_count.

  logic[FLIT_WIDTH-1:0] old_recv_cmd_in;
  logic recv_credit_q;      // registered credit (header and size flits)
  logic recv_payload_credit;
  logic recv_take;          // payload flit released by the router now
  word_t recv_drop_count;

  always @(posedge clock) begin
    old_recv_cmd_in <= ddma_if.recv_cmd_in;
  end

  assign recv_payload_credit = (rstate == RECEIVING_PAYLOAD) && (temp_flits_to_recv != 0)
                               && (recv_drop || istate == TOKEN_RECV);
  assign recv_take = recv_payload_credit && router_if.tx;
  assign router_if.credit_i = recv_credit_q | recv_payload_credit;
  assign mem_if.wb_in = (recv_take && !recv_drop) ? 4'b1111 : 4'b0000;

  always @(posedge clock) begin : RECEIVING
    if(~reset) begin
      case (rstate)

        RECEIVING_HEADER: begin // keep credit down until first flit arrives
          if(router_if.tx == 1) begin
            recv_credit_q <= 1;
            recv_drop <= (router_if.data_o[15:0] != ADDRESS[15:0]);
            rstate <= RECEIVING_SIZE_DELAYER;
          end else begin
            recv_credit_q <= 0;
          end
          temp_flits_to_recv <= 0;
        end

        RECEIVING_SIZE_DELAYER: begin
          recv_credit_q <= 0;
          if(router_if.tx == 1) begin
            rstate <= RECEIVING_SIZE;
          end
        end

        RECEIVING_SIZE: begin
          if(router_if.tx == 1) begin
            recv_credit_q <= 1;
            temp_flits_to_recv <= router_if.data_o;
            if (recv_drop) begin
              rstate <= RECEIVING_PAYLOAD_DELAY;   // no cpu interruption
            end else begin
              ddma_if.recv_size_out <= router_if.data_o;
              rstate <= RECEIVING_IRQ_ADDR;
            end
          end else begin
            recv_credit_q <= 0;
          end
        end

        RECEIVING_IRQ_ADDR: begin
          temp_recv_addr <= ddma_if.recv_addr_in;
          ddma_if.recv_addr_out <= ddma_if.recv_addr_in;
          recv_credit_q <= 0;
          if(ddma_if.recv_cmd_in != old_recv_cmd_in) begin
            rstate <= RECEIVING_PAYLOAD_DELAY;
          end
        end

        RECEIVING_PAYLOAD_DELAY: begin
          recv_credit_q <= 0;
          if (temp_flits_to_recv == 0) begin
            rstate <= recv_drop ? RECEIVING_HEADER : RECEIVING_HANDSHAKE;
            if (recv_drop) recv_drop_count <= recv_drop_count + 1;
          end else if (recv_drop || istate == TOKEN_RECV) begin
            rstate <= RECEIVING_PAYLOAD;   // wait for the memory token
          end
        end

        RECEIVING_PAYLOAD: begin
          recv_credit_q <= 0;
          if (recv_take) begin
            temp_recv_addr <= temp_recv_addr + 4;
            temp_flits_to_recv <= temp_flits_to_recv - 1;
            if (temp_flits_to_recv == 1) begin
              rstate <= recv_drop ? RECEIVING_HEADER : RECEIVING_HANDSHAKE;
              if (recv_drop) recv_drop_count <= recv_drop_count + 1;
            end
          end
        end

        RECEIVING_HANDSHAKE: begin
          recv_credit_q <= 0;
          if(ddma_if.recv_cmd_in != old_recv_cmd_in) begin
            rstate <= RECEIVING_HEADER;
          end
        end

        default: begin
          recv_credit_q <= 0;
          rstate <= RECEIVING_HEADER;
        end
      endcase
    end else begin
      rstate <= RECEIVING_HEADER;
      recv_credit_q <= 0;
      recv_drop <= 0;
      recv_drop_count <= 0;
      temp_recv_addr <= 0;
      temp_flits_to_recv <= 0;
    end
  end

  // export send/recv state to status register
  assign ddma_if.state_recv_out = rstate;
  assign ddma_if.state_send_out = sstate;

  // router input data always comes from the sending process, 
  // which reads data from the memory  
  assign mem_if.data_in = router_if.data_o;

  // memory always engit statabled, rx clock mirrors top clock
  assign router_if.clock_rx = clock;

  // keep sending interruption risen until cpu ack
  assign ddma_if.irq_send_out = (sstate == SENDING_HANDSHAKE);
  assign ddma_if.irq_recv_size_out = (rstate == RECEIVING_IRQ_ADDR);
  assign ddma_if.irq_recv_hshk_out = (rstate == RECEIVING_HANDSHAKE);

endmodule: ddma

