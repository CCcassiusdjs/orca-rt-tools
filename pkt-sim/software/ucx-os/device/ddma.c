#include <ucx.h>

// DDMA node identification
volatile uint32_t* DDMA_NODE_ADDR = (volatile uint32_t *)(0x20000000);
#define DDMA_NODE_DIMX ((* DDMA_NODE_ADDR & 0xFF000000) >> 24)
#define DDMA_NODE_DIMY ((* DDMA_NODE_ADDR & 0x00FF0000) >> 16)
#define DDMA_NODE_X ((* DDMA_NODE_ADDR & 0x0000FF00) >> 8)
#define DDMA_NODE_Y ((* DDMA_NODE_ADDR & 0x000000FF))

// DDMA send protocol
// DDMA_SEND_DEST_IN destination CPU (XY address)
// DDMA_SEND_PPTR_IN pointer to the packet to be sent
// DDMA_SEND_SIZE_IN number of flits to send 
// DDMA_SEND_CMD_IN  command to start the dma copy
volatile uint32_t* DDMA_SEND_DEST_IN = (volatile uint32_t *)(0x20000004); 
volatile uint32_t* DDMA_SEND_ADDR_IN = (volatile uint32_t *)(0x20000008);
volatile uint32_t* DDMA_SEND_SIZE_IN = (volatile uint32_t *)(0x2000000C);
volatile uint32_t* DDMA_SEND_CMD_IN  = (volatile uint32_t *)(0x20000010);

// DDMA status checking
volatile uint32_t* DDMA_STATUS = (uint32_t *)(0x20000014);

// DDMA recv protocol
// DDMA_RECV_ADDR_IN pointer to which write the packet
// DDMA_RECV_SIZE_OUT size of the current receiving packet (in flits)
// DDMA_RECV_CMD_IN cpu interruption acknowledgement
volatile uint32_t* DDMA_RECV_ADDR_IN  = (volatile uint32_t*)(0x20000018);
volatile uint32_t* DDMA_RECV_ADDR_OUT = (volatile uint32_t*)(0x2000001C);
volatile uint32_t* DDMA_RECV_SIZE_OUT = (volatile uint32_t*)(0x20000020);
volatile uint32_t* DDMA_RECV_CMD_IN   = (volatile uint32_t*)(0x20000024);


// linear node address: a = y * DIMX + x (inverse of _ddma_atox/_ddma_atoy)
uint32_t _ddma_node_addr(){
  return DDMA_NODE_Y * DDMA_NODE_DIMX + DDMA_NODE_X;
}

uint32_t _ddma_atox(uint32_t addr){
  return (addr % DDMA_NODE_DIMX);
}

uint32_t _ddma_atoy(uint32_t addr){
  return (addr / DDMA_NODE_DIMX);
}

uint32_t _ddma_xyta(uint32_t x, uint32_t y){
  return (x << 8) | y;
}

void _ddma_init(){
  printf("_ddma_init(): device info x:%d, y:%d, dimx:%d, dimy:%d\n", 
    DDMA_NODE_X, DDMA_NODE_Y, DDMA_NODE_DIMX, DDMA_NODE_DIMY);
}

uint32_t _ddma_send(uint32_t dest, uint32_t size, uint32_t* payload){
  *DDMA_SEND_DEST_IN = (_ddma_atox(dest) << 8) | _ddma_atoy(dest);
  
  // size is measured in flits, not bytes
  uint32_t data_size = (size % 4 == 0) ? (size / 4) : ((size / 4) + 1);

  *DDMA_SEND_SIZE_IN = data_size;
  *DDMA_SEND_ADDR_IN = (uint32_t) payload;
  *DDMA_SEND_CMD_IN  = 0x1; // starts dma copy
  return 0;
}

void _ddma_send_ack(){
  *DDMA_SEND_CMD_IN  = 0x0; // flag down 
}

uint8_t _ddma_send_status(){
  // printf("ddma_status_send: 0x%x\n", _ddma_status() >> 8);
  return _ddma_status() >> 8; // hi
}

uint16_t _ddma_status(){
  // printf("ddma_status: 0x%x\n", *DDMA_STATUS);
  return *DDMA_STATUS;
}

uint32_t _ddma_recv_size(){
  return *DDMA_RECV_SIZE_OUT;
}

void _ddma_set_recv_addr(uint32_t addr){
  *DDMA_RECV_ADDR_IN = addr;
}

uint32_t _ddma_get_recv_addr(){
  return *DDMA_RECV_ADDR_OUT;
}

void _ddma_recv_ack(){
  // printf("old reg 0x%x\n", *DDMA_RECV_CMD_IN);
  *DDMA_RECV_CMD_IN = !(*DDMA_RECV_CMD_IN);
  // printf("new reg 0x%x\n", *DDMA_RECV_CMD_IN);
}

