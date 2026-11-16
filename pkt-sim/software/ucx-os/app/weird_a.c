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

// ports 1 to 10; port 0 is the value of the unbound slots of the NoC
// driver table (lib/noc.c, pktdrv_ports)
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

// Release by tick (built with -DUCX_TICK_RELEASE, Makefile rule weird_a;
// lib/tick_release.c): task v waits for the tick of phase j + N_v before
// it reads the input of iteration j, so it runs at most once per phase and
// serves iteration j from the tick of phase j + n(v), as the phase model
// of the analysis (n(v) of rttools/bench_t/estimate.py, phases, for the
// dispatch order of the model: ABDF A B D F, C, EHI E H I, GJ J G). The
// release generator fires on the four PEs (app/weird_a.sim). Without the
// macro (rule weird_a_data) the code is the one of runs A to H: a task
// serves every iteration whose packets are in its queue.
#define N_A 0
#define N_B 0
#define N_C 1
#define N_D 0
#define N_E 2
#define N_F 0
#define N_G 1
#define N_H 2
#define N_I 2
#define N_J 3
#ifdef UCX_TICK_RELEASE
#define PHASE_WAIT(n, j) ucx_phase_wait((j) + (n))
#else
#define PHASE_WAIT(n, j)
#endif

// Time-triggered injection (built with -DUCX_NOC_TT, Makefile INJECTION=tt;
// lib/noc_tt.c): a packet to a task of another PE (A->C, C->E, F->G, H->J,
// I->J) leaves at the instant of the link schedule of the analysis flow,
// counted from the tick of the phase of the job that sends it
// (ucx_job_tick, lib/tick_release.c); app/weird_a_tt.h (rttools.ucxgen tt)
// holds the instant of each of these flows for the clock F_CPU of the
// build. Without the macro the job sends the packet at once (the images up
// to tag r11-rc5).
#ifdef UCX_NOC_TT
#include "weird_a_tt.h"
#define SEND_REMOTE(cpu, port, pkt, tag, at) \
  ucx_noc_send_at(cpu, port, pkt, tag, ucx_job_tick(), &(at))
#else
#define SEND_REMOTE(cpu, port, pkt, tag, at) ucx_noc_send(cpu, port, pkt, tag)
#endif

// Iteration markers (include/device/cacc.h): each task writes
// ITER_BEGIN(task, k) after it has the input of iteration k and
// ITER_END(task, k) after its last send of iteration k. The packets carry
// no iteration number (the tag is the COMM_*_WORKLOAD of the flow), so k
// is the count of passes of the loop of the task: every queue is FIFO and
// each producer sends one packet per iteration, so the k-th pass consumes
// the packet of iteration k. Iteration 1 is the first release of A.

// ------------------------------ TASK A
void task_a()
{
  ucx_noc_comm_create(PORT_A);
  noc_packet_t *pkt1 = create_pkt(COMM_AB_WORKLOAD);
  noc_packet_t *pkt2 = create_pkt(COMM_AC_WORKLOAD);

  int it = ITERATIONS;
  uint32_t k = 0;

  do {
#ifdef UCX_TICK_RELEASE
    // release of iteration k + 1: the tick of its phase
    PHASE_WAIT(N_A, k + 1);
#else
    // voluntary sleep
    kcb_p->tcb_p->state = TASK_BLOCKED;
    ucx_task_yield();
#endif
    ITER_BEGIN('A', ++k);

    // simulate processing
    ucx_sleep(TASK_A_WORKLOAD); 

    // tprintf("A->B\n");
    ucx_noc_send(CPU_B, PORT_B, pkt1, COMM_AB_WORKLOAD);

    // tprintf("A->C\n");
    SEND_REMOTE(CPU_C, PORT_C, pkt2, COMM_AC_WORKLOAD, TT_AT_A_C);
    ITER_END('A', k);
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
  uint32_t k = 0;
  
  do {
    PHASE_WAIT(N_B, k + 1);
    recv_and_print();
    ITER_BEGIN('B', ++k);
  
    // simulate processing
    ucx_sleep(TASK_B_WORKLOAD);

    // tprintf("B->D\n");
    ucx_noc_send(CPU_D, PORT_D, pkt, COMM_BD_WORKLOAD);
    ITER_END('B', k);

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
  uint32_t k = 0;

  do {
    PHASE_WAIT(N_C, k + 1);
    recv_and_print();
    ITER_BEGIN('C', ++k);

    // simulate processing
    ucx_sleep(TASK_C_WORKLOAD);

    // tprintf("C->E\n");
    SEND_REMOTE(CPU_E, PORT_E, pkt, COMM_CE_WORKLOAD, TT_AT_C_E);
    ITER_END('C', k);

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
  uint32_t k = 0;

  do {
    PHASE_WAIT(N_D, k + 1);
    recv_and_print();
    ITER_BEGIN('D', ++k);
    
    // simulate processing
    ucx_sleep(TASK_D_WORKLOAD);

    // tprintf("D->F\n");
    ucx_noc_send(CPU_F, PORT_F, pkt, COMM_DF_WORKLOAD);
    ITER_END('D', k);

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
  uint32_t k = 0;

  do 
  {
    PHASE_WAIT(N_E, k + 1);
    recv_and_print();
    ITER_BEGIN('E', ++k);

    // simulate processing
    ucx_sleep(TASK_E_WORKLOAD);

    // tprintf("E->I\n");
    ucx_noc_send(CPU_I, PORT_I, pkt1, COMM_EI_WORKLOAD);

    // tprintf("E->H\n");
    ucx_noc_send(CPU_H, PORT_H, pkt2, COMM_EH_WORKLOAD);
    ITER_END('E', k);

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
  uint32_t k = 0;

  do 
  {
    PHASE_WAIT(N_F, k + 1);
    recv_and_print();
    ITER_BEGIN('F', ++k);

    // simulate processing
    ucx_sleep(TASK_F_WORKLOAD);

    // tprintf("F->G\n");
    SEND_REMOTE(CPU_G, PORT_G, pkt, COMM_FG_WORKLOAD, TT_AT_F_G);
    ITER_END('F', k);
    
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
  uint32_t k = 0;

  do
  {
    PHASE_WAIT(N_G, k + 1);
    recv_and_print();
    ITER_BEGIN('G', ++k);

    // simulate processing
    ucx_sleep(TASK_G_WORKLOAD);

    // tprintf("G->J\n");
    ucx_noc_send(CPU_J, PORT_J, pkt, COMM_GJ_WORKLOAD);
    ITER_END('G', k);

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
  uint32_t k = 0;

  do
  {
    PHASE_WAIT(N_H, k + 1);
    recv_and_print();
    ITER_BEGIN('H', ++k);

    // simulate processing
    ucx_sleep(TASK_H_WORKLOAD);

    // tprintf("H->J\n");
    SEND_REMOTE(CPU_J, PORT_J, pkt, COMM_HJ_WORKLOAD, TT_AT_H_J);
    ITER_END('H', k);

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
  uint32_t k = 0;

  do
  {
    PHASE_WAIT(N_I, k + 1);
    recv_and_print();
    ITER_BEGIN('I', ++k);

    // simulate processing
    ucx_sleep(TASK_I_WORKLOAD);

    // tprintf("I->J\n");
    SEND_REMOTE(CPU_J, PORT_J, pkt, COMM_IJ_WORKLOAD, TT_AT_I_J);
    ITER_END('I', k);

  }  while (--it);

  ucx_free(pkt);
  sleep_forever();
}

// ------------------------------ TASK J
// J joins the flows G->J, H->J and I->J. Each producer sends one packet
// per iteration and every queue is FIFO, so the k-th packet of a producer
// belongs to iteration k. J runs iteration k after it has received the
// k-th packet of each of the three producers; a packet that arrives ahead
// of the slowest producer only increments the count of its producer.
#define J_INPUTS 3

// input of J that corresponds to the source port of a packet
int j_input(uint16_t source_port)
{
  switch (source_port) {
  case PORT_G: return 0;
  case PORT_H: return 1;
  case PORT_I: return 2;
  default:     return -1;
  }
}

// blocking receive as recv_and_print(); returns the source port
uint16_t recv_source_port()
{
  while(ucx_noc_probe() <= 0){
    kcb_p->tcb_p->state = TASK_BLOCKED;
    ucx_task_yield();
  }

  noc_packet_t *pkt = ucx_noc_receive();
  uint16_t port = pkt->source_port;

  if (pkt->source_node != ucx_noc_cpu_id())
    ucx_free(pkt);

  return port;
}

void task_j()
{
  ucx_noc_comm_create(PORT_J);

  // packets received from each input; iterations completed
  uint32_t received[J_INPUTS] = {0, 0, 0};
  uint32_t done = 0;

  int it = ITERATIONS;

  do
  {
    PHASE_WAIT(N_J, done + 1);
    // wait for the packet of iteration done + 1 from each input
    while (received[0] <= done || received[1] <= done || received[2] <= done) {
      uint16_t port = recv_source_port();
      int k = j_input(port);

      if (k < 0)
        printf("J: packet from unknown port %d\n", port);
      else
        received[k]++;
    }

    // simulate processing; J marks each iteration it runs, also the
    // second one of a run that serves two
    ITER_BEGIN('J', done + 1);
    ucx_sleep(TASK_J_WORKLOAD);
    done++;
    ITER_END('J', done);

  }while (--it);

  sleep_forever();
}

void idle_task_p(void)
{
#ifdef UCX_TICK_RELEASE
  // a yield can enter the idle task with interrupts disabled (kernel/sched.c)
  _ei();
#endif
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
