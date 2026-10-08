#include <ucx.h>

#define CPU_A 0
#define CPU_B 0
#define CPU_D 0
#define CPU_F 0

#define CPU_C 1

#define CPU_E 2
#define CPU_H 2
#define CPU_I 2

#define CPU_G 3
#define CPU_J 3

// cannot use port 0 (noc driver bug)
#define PORT_A 10
#define PORT_B 1
#define PORT_C 2
#define PORT_D 3
#define PORT_E 4
#define PORT_F 5
#define PORT_G 6
#define PORT_H 7
#define PORT_I 8
#define PORT_J 9

#define TASK_A_WORKLOAD 1230
#define TASK_B_WORKLOAD 4560
#define TASK_C_WORKLOAD 7890
#define TASK_D_WORKLOAD 1200
#define TASK_E_WORKLOAD 3450
#define TASK_F_WORKLOAD 6780
#define TASK_G_WORKLOAD 9010
#define TASK_H_WORKLOAD 2340
#define TASK_I_WORKLOAD 5670
#define TASK_J_WORKLOAD 8900

#define COMM_AC_WORKLOAD 1230
#define COMM_AB_WORKLOAD 4560
#define COMM_BD_WORKLOAD 7890
#define COMM_CE_WORKLOAD 1200
#define COMM_DF_WORKLOAD 3450
#define COMM_FG_WORKLOAD 6780
#define COMM_EI_WORKLOAD 9010
#define COMM_EH_WORKLOAD 2340
#define COMM_IJ_WORKLOAD 5670
#define COMM_HJ_WORKLOAD 8900
#define COMM_GJ_WORKLOAD 1230

// ------------------------------ TASKS
void recv_and_print()
{
  // idling until packet arrival
  while(ucx_noc_probe() <= 0){
      kcb_p->tcb_p->state = TASK_BLOCKED;
	    ucx_task_yield();
  }

  noc_packet_t *pkt = ucx_noc_receive();

  //  tprintf("<- %d:%d (from %d:%d)\n",
  //           pkt->source_node, pkt->source_port,
  //           pkt->target_node, pkt->target_port);

  // if packet came from other nodes, free memory
  // else, pointer should be freed as this would
  // break local sender
  if (pkt->source_node != ucx_noc_cpu_id())
    ucx_free(pkt);
}

noc_packet_t *create_pkt(uint32_t comm_workload)
{
  noc_packet_t *pkt_rec = ucx_noc_create_packet(comm_workload);

  for (int i = 0; i < comm_workload; i++)
    pkt_rec->data[i] = i;

  return pkt_rec;
}

void sleep_forever()
{
  kcb_p->tcb_p->state = TASK_STOPPED;
  ucx_task_yield();
}

#define ITERATIONS 99999

// ------------------------------ TASK A
void task_a()
{
  ucx_noc_comm_create(PORT_A);
  noc_packet_t *pkt1 = create_pkt(COMM_AB_WORKLOAD);
  noc_packet_t *pkt2 = create_pkt(COMM_AC_WORKLOAD);

  int it = ITERATIONS;

  do {
    // voluntary sleep
    kcb_p->tcb_p->state = TASK_BLOCKED;
    ucx_task_yield();

    // simulate processing
    ucx_sleep(TASK_A_WORKLOAD); 

    // tprintf("A->B\n");
    ucx_noc_send(CPU_B, PORT_B, pkt1, COMM_AB_WORKLOAD);

    // tprintf("A->C\n");
    ucx_noc_send(CPU_C, PORT_C, pkt2, COMM_AC_WORKLOAD);
  } while (--it);

  ucx_free(pkt1);
  ucx_free(pkt2);
  sleep_forever();
}

// ------------------------------ TASK B
void task_b()
{
  ucx_noc_comm_create(PORT_B);
  noc_packet_t *pkt = create_pkt(COMM_BD_WORKLOAD);

  int it = ITERATIONS;
  
  do {
    recv_and_print();
  
    // simulate processing
    ucx_sleep(TASK_B_WORKLOAD);

    // tprintf("B->D\n");
    ucx_noc_send(CPU_D, PORT_D, pkt, COMM_BD_WORKLOAD);

   } while (--it);

  ucx_free(pkt);
  sleep_forever();
}

// ------------------------------ TASK C
void task_c()
{
  printf("x\n");
  ucx_noc_comm_create(PORT_C);
  printf("x\n");
  noc_packet_t *pkt = create_pkt(COMM_CE_WORKLOAD);
  printf("x\n");

  int it = ITERATIONS;

  do {
    recv_and_print();

    // simulate processing
    ucx_sleep(TASK_C_WORKLOAD);

    // tprintf("C->E\n");
    ucx_noc_send(CPU_E, PORT_E, pkt, COMM_CE_WORKLOAD);

  }while (--it);

  ucx_free(pkt);
  sleep_forever();
}

// ------------------------------ TASK D
void task_d()
{
  ucx_noc_comm_create(PORT_D);
  noc_packet_t *pkt = create_pkt(COMM_DF_WORKLOAD);

  int it = ITERATIONS;

  do {
    recv_and_print();
    
    // simulate processing
    ucx_sleep(TASK_D_WORKLOAD);

    // tprintf("D->F\n");
    ucx_noc_send(CPU_F, PORT_F, pkt, COMM_DF_WORKLOAD);

  } while (--it);

  ucx_free(pkt);
  sleep_forever();
}

// ------------------------------ TASK E
void task_e()
{
  ucx_noc_comm_create(PORT_E);
  noc_packet_t *pkt1 = create_pkt(COMM_EI_WORKLOAD);
  noc_packet_t *pkt2 = create_pkt(COMM_EH_WORKLOAD);

  int it = ITERATIONS;

  do 
  {
    recv_and_print();

    // simulate processing
    ucx_sleep(TASK_E_WORKLOAD);

    // tprintf("E->I\n");
    ucx_noc_send(CPU_I, PORT_I, pkt1, COMM_EI_WORKLOAD);

    // tprintf("E->H\n");
    ucx_noc_send(CPU_H, PORT_H, pkt2, COMM_EH_WORKLOAD);

  }while (--it);

  ucx_free(pkt1);
  ucx_free(pkt2);
  sleep_forever();
}

// ------------------------------ TASK F
void task_f()
{
  ucx_noc_comm_create(PORT_F);
  noc_packet_t *pkt = create_pkt(COMM_FG_WORKLOAD);
  
  int it = ITERATIONS;

  do 
  {
    recv_and_print();

    // simulate processing
    ucx_sleep(TASK_F_WORKLOAD);

    // tprintf("F->G\n");
    ucx_noc_send(CPU_G, PORT_G, pkt, COMM_FG_WORKLOAD);
    
  }while (--it);

  ucx_free(pkt);
  sleep_forever();
}

// ------------------------------ TASK G
void task_g()
{
  ucx_noc_comm_create(PORT_G);
  noc_packet_t *pkt = create_pkt(COMM_GJ_WORKLOAD);

  int it = ITERATIONS;

  do
  {
    recv_and_print();

    // simulate processing
    ucx_sleep(TASK_G_WORKLOAD);

    // tprintf("G->J\n");
    ucx_noc_send(CPU_J, PORT_J, pkt, COMM_GJ_WORKLOAD);

  } while (--it);

  ucx_free(pkt);
  sleep_forever();
}

// ------------------------------ TASK H
void task_h()
{
  ucx_noc_comm_create(PORT_H);
  noc_packet_t *pkt = create_pkt(COMM_HJ_WORKLOAD);

  int it = ITERATIONS;

  do
  {
    recv_and_print();

    // simulate processing
    ucx_sleep(TASK_H_WORKLOAD);

    // tprintf("H->J\n");
    ucx_noc_send(CPU_J, PORT_J, pkt, COMM_HJ_WORKLOAD);

  } while (--it);

  ucx_free(pkt);
  sleep_forever();
}

// *((volatile int*)(0x20000050)) = 0x1;
// ------------------------------ TASK I
void task_i()
{
  ucx_noc_comm_create(PORT_I);
  noc_packet_t *pkt = create_pkt(COMM_IJ_WORKLOAD);

  int it = ITERATIONS;

  do
  {
    recv_and_print();

    // simulate processing
    ucx_sleep(TASK_I_WORKLOAD);

    // tprintf("I->J\n");
    ucx_noc_send(CPU_J, PORT_J, pkt, COMM_IJ_WORKLOAD);

  }  while (--it);

  ucx_free(pkt);
  sleep_forever();
}

// ------------------------------ TASK J
void task_j()
{
  ucx_noc_comm_create(PORT_J);

  int it = ITERATIONS;

  do
  {
    recv_and_print();
    recv_and_print();
    recv_and_print();

    // simulate processing
    ucx_sleep(TASK_J_WORKLOAD);

  }while (--it);

  sleep_forever();
}

void idle_task_p(void)
{
  // ucx_sleep(-1);
  for (;;)
    ;
}

int32_t app_main(void)
{

  uint32_t cpu_id = ucx_noc_cpu_id();

  // add idle task regardless of cpu id
  // note: idle must be ID=zero
  ucx_task_add(idle_task_p, "IDLE", DEFAULT_STACK_SIZE, 0, 0, 0);

  switch (cpu_id)
  {
  case 0: // ABDF
    ucx_task_add(task_f, "F", DEFAULT_STACK_SIZE, 0, 0, 0);
    ucx_task_add(task_d, "D", DEFAULT_STACK_SIZE, 0, 0, 0);
    ucx_task_add(task_b, "B", DEFAULT_STACK_SIZE, 0, 0, 0);
    ucx_task_add(task_a, "A", DEFAULT_STACK_SIZE, 0, 0, 0);
    break;
  case 1: // C
    ucx_task_add(task_c, "C", DEFAULT_STACK_SIZE, 0, 0, 0);
    break;
  case 2: // EHI
    ucx_task_add(task_h, "H", DEFAULT_STACK_SIZE, 0, 0, 0);
    ucx_task_add(task_i, "I", DEFAULT_STACK_SIZE, 0, 0, 0);
    ucx_task_add(task_e, "E", DEFAULT_STACK_SIZE, 0, 0, 0);
    break;
  case 3: // GJ
  default:
    ucx_task_add(task_j, "J", DEFAULT_STACK_SIZE, 0, 0, 0);
    ucx_task_add(task_g, "G", DEFAULT_STACK_SIZE, 0, 0, 0);
    break;
  }

  return 1;
}
