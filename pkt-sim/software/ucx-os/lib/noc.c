#include <ucx.h>

// binds tasks to ports
uint16_t pktdrv_ports[MAX_TASKS];

// queues of packets for each task
struct queue_s* pktdrv_tqueue[MAX_TASKS];

// Sink buffer for packets that cannot be stored (heap exhausted). The
// DDMA always writes the incoming packet to the address given in
// irq2; with no heap, it writes here and irq3 drops the packet.
#ifndef NOC_SINK_FLITS
#define NOC_SINK_FLITS 64
#endif
static uint32_t pktdrv_sink[NOC_SINK_FLITS];

// Gets the address of the current NoC node. Nodes are identified by
// their XY address, which is compressed in a 32-bit word such that
// XY = (X << 16) | Y;
uint32_t ucx_noc_cpu_id(void)
{
  return _ddma_node_addr();
}



void enable_receiver(uint16_t task_id){
  // locate receiver tasks and remove blocked state
  struct tcb_s* p = kcb_p->tcb_p;
  
  do {
    p = p->tcb_next;
  } while(p->id != task_id);

  p->state = TASK_READY;
}

// Implementation of the irq1_handler, intercepts 
// sending interruptions. While sending, the ddma 
// will interrupt the cpu to acknowledge the sending
// right after all the flits were transmitted.
void irq1_handler(void){
  _ddma_send_ack(); // flag down the cmd_in variable.
}

// Implementation of the irq2_handler, intercepts 
// receiving interruptions. Once the ddma receives the 
// size flit, it interrupts the cpu to acquire a pointer
// to the heap of the length of the packet. 
void irq2_handler(void){
  _di();
  uint32_t pkt_size = _ddma_recv_size(); // packet size in flits
  // printf("irq2_handler(): incoming packet of size %d (flits)\n", pkt_size);
  
  noc_packet_t* pkt = (noc_packet_t*) ucx_malloc(pkt_size * 4); // malloc in bytes
  // printf("irq2_handler(): ucx_malloc returned 0x%x\n", (uint32_t)pkt);

  if (pkt == NULL) {
    if (pkt_size > NOC_SINK_FLITS) {
      // no place to receive the packet: halt instead of corrupting memory
      printf("irq2_handler(): out of memory for %d flits, halting\n", pkt_size);
      for (;;);
    }
    printf("irq2_handler(): out of memory, packet will be dropped\n");
    pkt = (noc_packet_t*) pktdrv_sink;
  }

  _ddma_set_recv_addr((uint32_t)pkt); // send packet address to the ddma
  _ddma_recv_ack();
  _ei();
}

// Implementation of the irq3_handler, intercepts
// receiving interruptions. Once all flits were received, 
// interrupts the cpu to put the packet int the 
// right queue accordingly to its port.
void irq3_handler(void){

  // printf("lalalala <<<< \n");

  _di();
  noc_packet_t* pkt = (noc_packet_t*) _ddma_get_recv_addr();

  // packet received into the sink buffer (heap exhausted in irq2)
  if (pkt == (noc_packet_t*) pktdrv_sink)
  {
    printf("noc_driver_isr(): packet dropped (out of memory).\n");
  }
  // get rid of packets which address is not the same of this cpu
  else if (pkt->target_node != ucx_noc_cpu_id())
  {
    printf("noc_driver_isr(): wrong destination %x (expected %x).\n",
      pkt->target_node, ucx_noc_cpu_id());
    printf("noc_driver_isr(): packet at %x dropped.\n", pkt);
    ucx_free(pkt);
  } else {

    // get the queue associated to the port indicated in the packet
    // (only slots with an open comm count)
    int k;
    for (k = 0; k < MAX_TASKS; k++)
      if (pktdrv_tqueue[k] != NULL && pktdrv_ports[k] == pkt->target_port)
        break;

    if (k == MAX_TASKS)
    {
      printf("noc_driver_isr(): no task on port %d, dropping...\n",
        pkt->target_port);
      ucx_free(pkt);
    }
    // check whether the task has room for more packets in that queue
    else if (ucx_queue_enqueue(pktdrv_tqueue[k], pkt) != 0)
    {
      printf("noc_driver_isr(): task (on port %d) cannot receive more packets, dropping...\n", 
        pkt->target_port);
      ucx_free(pkt);
    }
    else
    {
      set_counter_4(pkt->tag);
      enable_receiver(k);
    }
  }
  _ddma_recv_ack();
  asm("nop;nop;");
  _ei();  
}


// PROBE!
int32_t ucx_noc_probe()
{
  uint16_t task_id;
  task_id = ucx_task_id();

  if (pktdrv_tqueue[task_id] == NULL)
    return UCX_NOC_TASK_NOT_BOUND;

  return ucx_queue_count(pktdrv_tqueue[task_id]);
}

// Initializes a queue of packets using one of the available ports. May a
// port be unavailable, the requested queue initialization will fail
// with ERR_COMM_UNFEASIBLE.
int32_t ucx_noc_comm_create(uint16_t port)
{
  _di();

  int task_id = ucx_task_id();

  // check whether this task has allocated a port before
  if (pktdrv_tqueue[task_id] != NULL) {
    _ei();
    return UCX_NOC_TASK_BIND_ALREADY;
  }

  // port already in use by another task (only slots with an open comm)
  for (int k = 0; k < MAX_TASKS; k++)
    if (pktdrv_tqueue[k] != NULL && pktdrv_ports[k] == port) {
      _ei();
      return UCX_NOC_PORT_BIND_ALREADY;
    }

  // add a new queue to receive packets for that task
  pktdrv_tqueue[task_id] = ucx_queue_create(MAX_PKT_QUEUE_SLOTS);

  // if we cannot create a new queue due to unavailable memory
  // space, return ERR_OUT_OF_MEMORY
  if (pktdrv_tqueue[task_id] == NULL) {
    _ei();
    return UCX_NOC_OUT_OF_MEMORY;
  }

  // connect the port to the task and return ERR_OK
  pktdrv_ports[task_id] = port;
  printf("ucx_noc_comm_create(): task %d connected on port %d\n", task_id, port);
  _ei();
  return UCX_NOC_OK;
  

  
}

// Destroys a connection, removing the
uint32_t ucx_noc_comm_destroy(uint16_t port)
{

  _di();
  int task_id = ucx_task_id();

  if (pktdrv_tqueue[task_id] == NULL) {
    _ei();
    return UCX_NOC_TASK_NOT_BOUND;
  }

  // removes all elements from the comm queue, adding them
  // to the queue of shared packets
  while (ucx_queue_count(pktdrv_tqueue[task_id])){
    noc_packet_t* pkt = ucx_queue_dequeue(pktdrv_tqueue[task_id]);
    ucx_free(pkt);
    //ucx_queue_enqueue(pktdrv_queue, ucx_queue_dequeue(pktdrv_tqueue[task_id]));
  }


  // check whether the comm queue was gracefully destroyed. If not,
  // return ERR_COMM_ERROR
  if (ucx_queue_destroy(pktdrv_tqueue[task_id])) {
    _ei();
    return UCX_NOC_UNABLE_TO_DESTROY;
  }

  pktdrv_tqueue[task_id] = NULL;
  pktdrv_ports[task_id] = 0;

  _ei();

  return UCX_NOC_OK;
}

// initializes the driver
void noc_driver_init(void)
{
  // init hardware
  _ddma_init();

  // print out node id (from MMIO)
  printf("noc_driver_init(): this is core #%d\n", ucx_noc_cpu_id());
  
  // allocate a new queue of packets
  //pktdrv_queue = ucx_queue_create(MAX_PKT_QUEUE_SLOTS);
  for (int32_t i = 0; i < MAX_TASKS; i++){
    pktdrv_ports[i] = 0;
    pktdrv_tqueue[i] = NULL;
  }

  // if (pktdrv_queue == NULL){
  //   printf("noc_driver_init(): unable to create packet queue\n");
  // } else {

  //   // make sure no port is allocated at time zero 
  //   // for (int32_t i = 0; i < MAX_TASKS; i++) 
  //   //   pktdrv_ports[i] = 0;
    
  //   // print out the address of handlers
  //   // printf("noc_driver_init(): noc driver send irq handler at 0x%0x\n", &irq1_handler);
  //   // printf("noc_driver_init(): noc driver recv irq handler at 0x%0x\n", &irq2_handler);
  //   // printf("noc_driver_init(): noc driver recv irq handler at 0x%0x\n", &irq3_handler);
  // }

  // enable irq pins 1 (sending) and 2 (receiving)
  IRQ_MASK |= MASK_IRQ1 | MASK_IRQ2 | MASK_IRQ3;
}


/**
 * @brief Receives a message from a task (blocking receive).
 *
 * @param source_cpu is a pointer to a variable which will hold the source cpu
 * @param source_port is a pointer to a variable which will hold the source port
 * @param buf is a pointer to a buffer to hold the received message
 * @param size a pointer to a variable which will hold the size (in bytes) of the received message
 * @param channel is the selected message channel of this message (must be the same as in the sender)
 *
 * @return ERR_OK when successful, ERR_COMM_UNFEASIBLE when no message queue (comm) was
 * created and ERR_SEQ_ERROR when received packets arrive out of order, so the message
 * is corrupted.
 *
 * A message is build from packets received on the ni_isr() routine. Packets are decoded and
 * combined in a complete message, returning the message, its size and source identification
 * to the calling task. The buffer where the message will be stored must be large enough or
 * we will have a problem that may not be noticed before its too late.
 */
noc_packet_t* ucx_noc_receive()
{
  int task_id;
  task_id = ucx_task_id();

  if (pktdrv_tqueue[task_id] == NULL){
    printf("ucx_noc_receive(): unable to receive from NULL queue\n");
    return NULL;
  }

  if (ucx_queue_count(pktdrv_tqueue[task_id]) == 0){
    printf("ucx_noc_receive(): unable to receive from empty queue\n");
    return NULL;
  }

  return ucx_queue_dequeue(pktdrv_tqueue[task_id]);
}

/**
 * Request a new persistent data container from the heap to store a new 
 * package. The container has increased size as we need append the header
 * to it. This contrainer must be freed by the user.
 * 
 * @size number of bytes for the payload
*/
noc_packet_t* ucx_noc_create_packet(uint32_t size){
  _di();
  // malloc once by allocating enough space for the 
  // packet structure and its data  
  
  uint32_t payload_size = (size % 4 == 0) 
                        ? size 
                        : size + (4 - (size % 4));

  noc_packet_t* pkt = (noc_packet_t*) ucx_malloc(sizeof(noc_packet_t) + payload_size);

  if(pkt){
    // e.g. 6 bytes =>> 6 + (4 - 2) = 8 (multiple of 4)
    pkt->payload_size = payload_size;
    pkt->source_node = ucx_noc_cpu_id();
    pkt->source_port = pktdrv_ports[ucx_task_id()];
    pkt->target_node = 0;
    pkt->target_port = 0;
    pkt->tag = 0;
  } else {
    printf("ucx_noc_create_packet(): unable to malloc\n");
  }
  _ei();
  return pkt;
};

/**
 * @brief Sends a message to a task (blocking send).
 *
 * @param target_cpu is the target processor
 * @param target_port is the target task port
 * @param pkt is a pointer to a packet 
 * @param tag user-defined tag
 *
 * @return ERR_OK
 *
 * A message is broken into packets containing a header and part of the message as the payload.
 * The packets are injected, one by one, in the network through the network interface.
 */
uint32_t ucx_noc_send(uint16_t target_cpu, uint16_t target_port, 
  noc_packet_t* pkt, uint16_t tag)
{
  pkt->target_node = target_cpu;
  pkt->target_port = target_port;
  pkt->tag = tag;

  set_counter_3(pkt->tag);

  //check whether the packet destination lies in the same pcore
  if(target_cpu != ucx_noc_cpu_id()) {
    // prevent user from sending another packet until the 
    // ddma gets ready again (0x1 is the idle state)
    while(_ddma_send_status() != 0x1);

    // send async
    return _ddma_send(target_cpu, sizeof(noc_packet_t) + pkt->payload_size,
      (uint32_t*)pkt);

  // TODO: push packets into the private queue
  } else {
    // printf("ucx_noc_send(): packet with same source/destination\n");
    
    // test whether the target port has a comm open
    int target_task = -1;

    // only slots with an open comm count (unbound slots keep port 0)
    for (int i = 0; i < MAX_TASKS; i++)
      if (pktdrv_tqueue[i] != NULL && pktdrv_ports[i] == target_port)
        target_task = i;

    if(target_task == -1) {
      printf("could not deliver pkt, task has no comm open.\n");
      return UCX_NOC_PORT_HAS_NO_TASK;
    }
    
    if (pktdrv_tqueue[target_task] == NULL) {
      printf("wut error.\n");
      return UCX_NOC_WUT;
    }

    // wake the receiver only when the packet entered its queue
    int32_t res = ucx_queue_enqueue(pktdrv_tqueue[target_task], pkt);
    if (res == 0) {
      set_counter_4(pkt->tag);
      enable_receiver(target_task);
    }
    return res;
  }
}
