/* Application of exp-23 (app/weird_a.c) with lib/noc.c.
 *
 * E (node 2) sends to I the packet of COMM_EI_WORKLOAD bytes with tag
 * COMM_EI_WORKLOAD (it sent tag COMM_DF_WORKLOAD).
 * J (node 3) runs iteration k after the k-th packet of each of G, H and I
 * (it ran after any three packets).
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

/* ------------------------------------------------------------ join of J */

#define J_ID 1
#define G_ID 2

static noc_packet_t *g_pkt;

/* G is on the node of J: local send, as task_g does */
static void send_g(void)
{
	host_current_task = G_ID;
	ucx_noc_send(CPU_J, PORT_J, g_pkt, COMM_GJ_WORKLOAD);
	host_current_task = J_ID;
	host_delivered++;
}

static void send_h(void) { deliver(CPU_H, PORT_H, PORT_J, COMM_HJ_WORKLOAD); }
static void send_i(void) { deliver(CPU_I, PORT_I, PORT_J, COMM_IJ_WORKLOAD); }

/* batches of arrivals separated by '|'; at most 7 packets wait in the
 * queue of J (lib/queue.c: dequeue of a full queue of 8 returns NULL) */
static const char *j_script;

static int j_block(void)
{
	if (!*j_script)
		return 0;
	for (; *j_script && *j_script != '|'; j_script++) {
		switch (*j_script) {
		case 'G': send_g(); break;
		case 'H': send_h(); break;
		case 'I': send_i(); break;
		}
	}
	if (*j_script == '|')
		j_script++;
	return 1;
}

/* runs J on the arrivals of `script` and returns the number of
 * iterations; consumed[k] = packets received when iteration k + 1 ran */
static int run_j(const char *script, int *consumed)
{
	setup(1, 1, 3);                             /* node 3: IDLE, J, G */
	CHECK(ucx_noc_cpu_id() == CPU_J);
	host_current_task = G_ID;
	CHECK(ucx_noc_comm_create(PORT_G) == UCX_NOC_OK);
	g_pkt = create_pkt(COMM_GJ_WORKLOAD);

	host_current_task = J_ID;
	j_script = script;
	host_on_block = j_block;
	if (!setjmp(host_leave))
		task_j();

	for (int k = 0; k < host_sleeps && k < 16; k++) {
		CHECK(host_sleep_cycles[k] == TASK_J_WORKLOAD);
		consumed[k] = host_sleep_consumed[k];
	}
	host_current_task = J_ID;
	CHECK(ucx_noc_probe() == 0);
	return host_sleeps;
}

/* a producer ahead of the others: the third packet (G of iteration 2)
 * does not complete iteration 1 */
static void test_j_joins_same_iteration(void)
{
	int c[16];
	int n = run_j("GHGIHGI|HIGHI", c);
	CHECK(n == 4);
	CHECK(c[0] == 4);      /* G1 H1 G2 I1 */
	CHECK(c[1] == 7);      /* H2 G3 I2 */
	CHECK(c[2] == 9);      /* | H3 I3 */
	CHECK(c[3] == 12);     /* G4 H4 I4 */
}

/* H two iterations ahead, then I completes two iterations in a row */
static void test_j_producer_ahead(void)
{
	int c[16];
	int n = run_j("HHHGGII|IG", c);
	CHECK(n == 3);
	CHECK(c[0] == 6);      /* ... I1 */
	CHECK(c[1] == 7);      /* I2 */
	CHECK(c[2] == 9);      /* | I3 G3 */
}

/* arrivals in the order of the producers: one iteration per three packets */
static void test_j_in_order(void)
{
	int c[16];
	int n = run_j("GHI|HIG|IGH", c);
	CHECK(n == 3);
	CHECK(c[0] == 3);
	CHECK(c[1] == 6);
	CHECK(c[2] == 9);
}

/* packets of an unknown port do not count */
static void test_j_unknown_port(void)
{
	int c[16];
	run_j("", c);                               /* setup of node 3 */
	host_current_task = J_ID;
	deliver(CPU_C, PORT_C, PORT_J, COMM_CE_WORKLOAD);
	send_g();
	send_h();
	j_script = "I";
	host_on_block = j_block;
	host_sleeps = 0;
	if (!setjmp(host_leave))
		task_j();
	CHECK(host_sleeps == 1);
	CHECK(host_sleep_consumed[0] == 4);
}

int main(void)
{
	RUN_FORK(test_e_sends_ei_workload);
	RUN_FORK(test_j_joins_same_iteration);
	RUN_FORK(test_j_producer_ahead);
	RUN_FORK(test_j_in_order);
	RUN_FORK(test_j_unknown_port);
	DONE();
}
