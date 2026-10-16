#include <ucx.h>

#define CMPX_PKT_SIZE 1600
#define CMPX_WORKLOAD 61760

#define SQRE_PKT_SIZE 1024
#define SQRE_WORKLOAD 361

#define GTHR_PKT_SIZE 1024
#define GTHR_WORKLOAD 202

#define ANON_WORKLOAD 36480


// node 0
void task_complex(void)
{
  ucx_noc_comm_create(8);

  // // receive packets 
  // // -- no packet to receive --

  // // processing
  tprintf("processing\n");
  ucx_sleep(CMPX_WORKLOAD);

  // send packets
  tprintf("sending\n");
  noc_packet_t* pkt = ucx_noc_create_packet(CMPX_PKT_SIZE);
  for(int i = 0; i < pkt->payload_size; i++)
    pkt->data[i] = (i % 24) + 65;
  
  ucx_noc_send(1, 8, pkt, 0); // to 1, task_square
  
  // sleeps indefinitely
  tprintf("done\n");
  ucx_sleep(-1);
}

// node 1
void task_square(void)
{
  ucx_noc_comm_create(8);
  
  // probe
  tprintf("probing\n");
  while(ucx_noc_probe() <= 0);
  
  // receiving
  noc_packet_t* pkt_rec = ucx_noc_receive();
  tprintf("recved from %d:%d\n", pkt_rec->source_node, pkt_rec->source_port);
  ucx_free(pkt_rec);

  // processing
  tprintf("processing\n");
  ucx_sleep(SQRE_WORKLOAD);
  
  // send packets
  tprintf("sending\n");
  noc_packet_t* pkt = ucx_noc_create_packet(SQRE_PKT_SIZE);
  for(int i = 0; i < SQRE_PKT_SIZE; i++)
    pkt->data[i] = 0;

  ucx_noc_send(2, 8, pkt, 0);
  
  // hangs indefinitely
  tprintf("done\n");
  ucx_sleep(-1);
}


//node 2
void task_gather(void)
{
  ucx_noc_comm_create(8);
  
  // receive packets
  tprintf("probing\n");
  while(ucx_noc_probe() <= 0);
  
  noc_packet_t* pkt_rec = ucx_noc_receive();
  tprintf("recved from %d:%d\n", pkt_rec->source_node, pkt_rec->source_port);
  ucx_free(pkt_rec);
  
  // processing
  ucx_sleep(GTHR_WORKLOAD);
  tprintf("processing\n");

  // send packets
  tprintf("sending\n");
  noc_packet_t* pkt = ucx_noc_create_packet(GTHR_PKT_SIZE);
  for(int i = 0; i < GTHR_PKT_SIZE; i++)
    pkt->data[i] = 0;

  ucx_noc_send(3, 8, pkt, 0);
  
  // hangs indefinitely
  tprintf("done\n");
  ucx_sleep(-1);
}


//node 3
void task_afilter(void)
{
  ucx_noc_comm_create(8);  

  // receive packets 
  tprintf("probing\n");
  while(ucx_noc_probe() <= 0);
  
  noc_packet_t* pkt_rec = ucx_noc_receive();
  tprintf("recved from %d:%d\n", pkt_rec->source_node, pkt_rec->source_port);
  ucx_free(pkt_rec);

  // processing
  tprintf("processing\n");
  ucx_sleep(ANON_WORKLOAD);
  
  // // send packets
  // // -- nothing to send -- 

  // hangs indefinitely
  tprintf("done\n");
  ucx_sleep(-1);
}

void idle_task_p(void){
  // ucx_sleep(-1);
  for(;;);
}

int32_t app_main(void){

  uint32_t cpu_id = ucx_noc_cpu_id();
  
  switch (cpu_id){
    case 0: // Complex Source
      ucx_task_add(task_complex, "CMPX", DEFAULT_STACK_SIZE,0,0,0);
      break;
    case 1: // Square and Scale
      ucx_task_add(task_square, "SQRE", DEFAULT_STACK_SIZE,0,0,0);
      break;
    case 2: // CFAR Gather
      ucx_task_add(task_gather, "GTHR", DEFAULT_STACK_SIZE,0,0,0);
      break;
    case 3: // Anon Filter A (node 3)
      ucx_task_add(task_afilter, "ANON", DEFAULT_STACK_SIZE,0,0,0);
      break;
    default: 
      ucx_task_add(idle_task_p, "IDLE", DEFAULT_STACK_SIZE,0,0,0);    
      break;
  }  

	return 1;
}
