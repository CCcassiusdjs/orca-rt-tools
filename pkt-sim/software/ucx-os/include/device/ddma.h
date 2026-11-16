// returns the identifier of this node (node number),
// which is unique per pe. XY identifiers are 
// available through memory-mapped I/O, and address
// identifier is done through software conversion.
uint32_t _ddma_node_addr();

// initialize ddma registers and print test routine output
void _ddma_init();

// copies a packet from the memory into the network. copy 
// is performed in a dma fashion
uint32_t _ddma_send(uint32_t dest, uint32_t size, uint32_t* payload);
void _ddma_send_ack();

// conversions of _ddma_send (XY address of a node, flits of a packet of
// `size` bytes) and the send with converted values (lib/noc_tt.c)
uint32_t _ddma_dest_xy(uint32_t dest);
uint32_t _ddma_flits(uint32_t size);
void _ddma_send_xy(uint32_t xy, uint32_t flits, uint32_t* payload);

// recv
uint32_t* _ddma_recv_ptr_out();

// 8-bit register
// ---------------------------------
// | s | r | S | S | S | R | R | R |
// ---------------------------------
//   0   1   2   3   4   5   6   7

// [4:2] send state machine status 
// [7:5] recv state machine status 
// [0]   send proc. irq
// [1]   recv. proc. irq

// send process state machine states codes
// WAIT_CONFIG = 0
// SENDING_HEADER = 1
// SENDING_SIZE = 2
// SENDING_PAYLOAD = 3
// HANDSHAKE = 4

// recv process state machine states 
// IDLE_REC = 0,
// REC_HEADER = 1,
// REC_SIZE = 2,
// REC_PAYLOAD = 3,
// IRQ_REC = 4,
// REC_HEADER_SYNC = 5
uint16_t _ddma_status();

uint8_t _ddma_send_status();



#define DDMA_SEND_ACTIVE 0xC0
#define DDMA_RECV_ACTIVE 0x30


uint32_t _ddma_recv_size(void);
void _ddma_set_recv_addr(uint32_t);
uint32_t _ddma_get_recv_addr(void);
void _ddma_recv_ack(void);
