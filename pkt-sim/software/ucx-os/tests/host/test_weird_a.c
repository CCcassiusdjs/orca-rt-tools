/* Application of exp-23 (app/weird_a.c) with lib/noc.c.
 *
 * E (node 2) sends to I the packet of COMM_EI_WORKLOAD bytes with tag
 * COMM_EI_WORKLOAD (it sent tag COMM_DF_WORKLOAD).
 *
 * The task runs until it blocks on an empty queue; then ucx_task_yield()
 * delivers the next batch of packets or leaves the task with longjmp. */
#include <ucx.h>
#include "host_test.h"

#define TASK_STOPPED 0
#define DEFAULT_STACK_SIZE 2048

void irq3_handler(void);

static jmp_buf host_leave;
static int (*host_on_block)(void);   /* 0: leave the task */
static int host_delivered;           /* packets delivered to the running task */
static int host_sleeps;
static int32_t host_sleep_cycles[16];
static int host_sleep_consumed[16];  /* packets consumed at each ucx_sleep */

void ucx_task_yield(void)
{
	if (!host_on_block || !host_on_block())
		longjmp(host_leave, 1);
}

void ucx_sleep(int32_t cycles)
{
	if (host_sleeps < 16) {
		host_sleep_cycles[host_sleeps] = cycles;
		host_sleep_consumed[host_sleeps] = host_delivered - ucx_noc_probe();
	}
	host_sleeps++;
}

int32_t ucx_task_add(void *task, char *name, uint16_t stack_size, uint16_t period,
	uint16_t capacity, uint16_t deadline)
{
	return 0;
}

#include "../../app/weird_a.c"

static void setup(uint32_t x, uint32_t y, int tasks)
{
	host_arena_init();
	host_ddma_map(2, 2, x, y);
	host_tasks_init(tasks);
	noc_driver_init();
	host_irq_enabled = 1;
	host_on_block = NULL;
	host_delivered = 0;
	host_sleeps = 0;
}

/* packet from another node: irq2 (size) and irq3 (complete packet) */
static void deliver(uint16_t src_node, uint16_t src_port, uint16_t port, uint16_t tag)
{
	host_ddma_regs[8] = 4;                      /* 4 flits = 16 bytes */
	irq2_handler();
	noc_packet_t *pkt = (noc_packet_t *)(uintptr_t)host_ddma_regs[6];
	CHECK(pkt != NULL);
	if (!pkt)
		return;
	pkt->source_node = src_node;
	pkt->target_node = ucx_noc_cpu_id();
	pkt->source_port = src_port;
	pkt->target_port = port;
	pkt->payload_size = 4;
	pkt->tag = tag;
	host_ddma_regs[7] = host_ddma_regs[6];      /* RECV_ADDR_OUT */
	irq3_handler();
	host_delivered++;
}

/* ------------------------------------------------------------- E -> I */

#define E_ID 3
#define H_ID 1
#define I_ID 2

static int e_batches;

static int e_block(void)
{
	if (e_batches++ > 0)
		return 0;
	deliver(CPU_C, PORT_C, PORT_E, COMM_CE_WORKLOAD);
	return 1;
}

static void test_e_sends_ei_workload(void)
{
	setup(0, 1, 4);                             /* node 2: IDLE, H, I, E */
	CHECK(ucx_noc_cpu_id() == CPU_E);
	host_current_task = H_ID;
	CHECK(ucx_noc_comm_create(PORT_H) == UCX_NOC_OK);
	host_current_task = I_ID;
	CHECK(ucx_noc_comm_create(PORT_I) == UCX_NOC_OK);

	host_current_task = E_ID;
	e_batches = 0;
	host_on_block = e_block;
	if (!setjmp(host_leave))
		task_e();

	CHECK(host_sleeps == 1);
	CHECK(host_sleep_cycles[0] == TASK_E_WORKLOAD);

	host_current_task = I_ID;
	CHECK(ucx_noc_probe() == 1);
	noc_packet_t *p = ucx_noc_receive();
	CHECK(p && p->tag == COMM_EI_WORKLOAD);
	CHECK(p && p->payload_size >= COMM_EI_WORKLOAD);
	CHECK(p && p->target_port == PORT_I && p->source_port == PORT_E);

	host_current_task = H_ID;
	CHECK(ucx_noc_probe() == 1);
	p = ucx_noc_receive();
	CHECK(p && p->tag == COMM_EH_WORKLOAD);
	CHECK(p && p->payload_size >= COMM_EH_WORKLOAD);
}

int main(void)
{
	RUN_FORK(test_e_sends_ei_workload);
	DONE();
}
