/* Release by tick (lib/tick_release.c) and application E built with it
 * (app/weird_a.c, -DUCX_TICK_RELEASE; run.sh also builds lib/noc.c with
 * the macro).
 *
 * 1. Tick hook: each release interrupt counts one phase; the tick applies
 *    the counted phases and readies the blocked tasks whose phase has
 *    come, and only those.
 * 2. ucx_phase_wait(p): returns at once when the phase index is at or
 *    above p and above the phase of the previous start of the task;
 *    otherwise the task blocks (with interrupts disabled at the yield)
 *    until a tick reaches that phase. A second call in the same phase
 *    blocks until the next phase.
 * 3. Driver: a packet arrival does not wake a task that waits for a
 *    phase; it wakes a task blocked on its queue.
 * 4. Task E (n(E) = 2) with the packets of iterations 1 and 2 of C in its
 *    queue: one iteration per phase, iteration j from phase j + 2.
 * 5. Task J (n(J) = 3): arrivals of H and I do not wake it before the tick
 *    of phase j + 3; it serves iteration j in that phase.
 * 6. Task A: one iteration per release, from the tick after it. */
#include <ucx.h>
#include "host_test.h"

#define TASK_STOPPED 0
#define DEFAULT_STACK_SIZE 2048

void irq3_handler(void);

static jmp_buf host_leave;
static int (*host_on_block)(void);   /* 0: leave the task */
static int host_sleeps;
static uint32_t host_sleep_phase[16];
static int host_yield_irq[16];       /* interrupt state at each yield */
static int host_yields;

void ucx_task_yield(void)
{
	if (host_yields < 16)
		host_yield_irq[host_yields] = host_irq_enabled;
	host_yields++;
	if (!host_on_block || !host_on_block())
		longjmp(host_leave, 1);
}

int32_t ucx_task_add(void *task, char *name, uint16_t stack_size, uint16_t period,
	uint16_t capacity, uint16_t deadline)
{
	return 0;
}

#include "../../lib/tick_release.c"

void ucx_sleep(int32_t cycles)
{
	if (host_sleeps < 16)
		host_sleep_phase[host_sleeps] = ucx_phase();
	host_sleeps++;
}

#include "../../app/weird_a.c"

static void setup(uint32_t x, uint32_t y, int tasks)
{
	host_arena_init();
	host_ddma_map(2, 2, x, y);
	host_ddma_regs[5] = 0x100;                  /* DDMA send idle */
	host_tasks_init(tasks);
	noc_driver_init();
	host_irq_enabled = 1;
	host_on_block = NULL;
	host_sleeps = 0;
	host_yields = 0;
	host_iter_nmarks = 0;
	tr_pending = 0;
	tr_phase = 0;
	for (int i = 0; i < MAX_TASKS; i++)
		tr_wait[i] = tr_last[i] = 0;
}

/* n release interrupts (irq4_handler counts them in tr_pending; its
 * acknowledge register does not exist on the host), then one tick */
static void phases(int n)
{
	tr_pending += n;
	ucx_app_tick();
}

/* packet from another node: irq2 (size) and irq3 (complete packet) */
static void deliver(uint16_t src_node, uint16_t src_port, uint16_t port, uint16_t tag)
{
	host_ddma_regs[8] = 4;                      /* 4 flits = 16 bytes */
	host_isr(irq2_handler);
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
	host_isr(irq3_handler);
}

/* the markers written so far are `n` words of `expected` */
static int marks_are(const uint32_t *expected, int n)
{
	if (host_iter_nmarks != n)
		return 0;
	for (int i = 0; i < n; i++)
		if (host_iter_marks[i] != expected[i])
			return 0;
	return 1;
}

/* ------------------------------------------- 1. tick hook */

static void test_tick_hook(void)
{
	setup(0, 0, 4);
	for (int i = 1; i < 4; i++)
		CHECK(host_task_state(i) == TASK_BLOCKED);
	tr_wait[1] = 1;                             /* waits for phase 1 */
	tr_wait[2] = 3;                             /* waits for phase 3 */
	ucx_app_tick();                             /* a tick without release: phase 0 */
	CHECK(ucx_phase() == 0 && host_task_state(1) == TASK_BLOCKED);
	phases(1);
	CHECK(ucx_phase() == 1);
	CHECK(host_task_state(1) == TASK_READY);
	CHECK(host_task_state(2) == TASK_BLOCKED);  /* phase 3 not reached */
	CHECK(host_task_state(3) == TASK_BLOCKED);  /* blocked on its queue: not a phase wait */
	phases(2);                                  /* two releases before one tick */
	CHECK(ucx_phase() == 3 && host_task_state(2) == TASK_READY);
	CHECK(host_task_state(3) == TASK_BLOCKED);
	CHECK(ucx_phase_waiting(2) && !ucx_phase_waiting(3) && !ucx_phase_waiting(MAX_TASKS));
}

/* ------------------------------------------- 2. phase wait */

static int wait_script[8];   /* releases applied at each block, -1: leave */
static int wait_blocks;

static int wait_block(void)
{
	int r = wait_script[wait_blocks < 8 ? wait_blocks : 7];

	wait_blocks++;
	CHECK(host_task_state(host_current_task) == TASK_BLOCKED);
	CHECK(!host_irq_enabled);                   /* test and block without interrupts */
	CHECK(tr_wait[host_current_task] != 0);
	if (r < 0)
		return 0;
	phases(r);
	return 1;
}

static void script(int a, int b, int c, int d)
{
	wait_script[0] = a; wait_script[1] = b; wait_script[2] = c;
	for (int i = 3; i < 8; i++)
		wait_script[i] = d;
	wait_blocks = 0;
}

static void test_phase_wait(void)
{
	setup(0, 0, 4);
	host_set_current(2);
	host_on_block = wait_block;

	script(1, -1, -1, -1);
	CHECK(ucx_phase_wait(1) == 1);              /* blocks until the tick of phase 1 */
	CHECK(wait_blocks == 1 && host_irq_enabled && tr_wait[2] == 0 && tr_last[2] == 1);

	script(1, -1, -1, -1);
	CHECK(ucx_phase_wait(1) == 2);              /* started in phase 1: next phase */
	CHECK(wait_blocks == 1);

	script(1, 1, 1, -1);
	CHECK(ucx_phase_wait(5) == 5);              /* three blocks, one release each */
	CHECK(wait_blocks == 3);

	phases(2);                                  /* phase 7, no start in 6 and 7 */
	script(-1, -1, -1, -1);
	CHECK(ucx_phase_wait(6) == 7);              /* phase reached: no block */
	CHECK(wait_blocks == 0 && host_irq_enabled);

	/* a tick without release does not wake the task */
	script(0, 0, -1, -1);
	int left = 0;
	if (!setjmp(host_leave))
		ucx_phase_wait(8);
	else
		left = 1;
	CHECK(left && wait_blocks == 3 && ucx_phase() == 7);
	CHECK(host_task_state(2) == TASK_BLOCKED && tr_wait[2] == 8);
}

/* ------------------------------------------- 3. driver */

static void test_arrival_does_not_wake_a_phase_wait(void)
{
	setup(0, 1, 4);                             /* node 2: IDLE, H, I, E */
	host_set_current(3);
	CHECK(ucx_noc_comm_create(PORT_E) == UCX_NOC_OK);
	host_set_current(1);
	CHECK(ucx_noc_comm_create(PORT_H) == UCX_NOC_OK);
	tr_wait[3] = 4;                             /* E waits for phase 4 */
	deliver(CPU_C, PORT_C, PORT_E, COMM_CE_WORKLOAD);
	CHECK(host_task_state(3) == TASK_BLOCKED);  /* queued, not woken */
	host_set_current(3);
	CHECK(ucx_noc_probe() == 1);
	deliver(CPU_E, PORT_E, PORT_H, COMM_EH_WORKLOAD);
	CHECK(host_task_state(1) == TASK_READY);    /* H blocked on its queue: woken */
	phases(4);
	CHECK(host_task_state(3) == TASK_READY);
}

/* ------------------------------------------- 4. E: one iteration per phase */

#define E_ID 3
#define H_ID 1
#define I_ID 2

static int e_blocks;

static int e_block(void)
{
	e_blocks++;
	if (e_blocks == 1) {
		/* phase 0: E waits for phase 1 + n(E) = 3 */
		CHECK(host_sleeps == 0 && tr_wait[E_ID] == 3);
		phases(3);
		return 1;
	}
	if (e_blocks == 2) {
		/* iteration 1 ran in phase 3; the packet of iteration 2 waits in the queue */
		CHECK(host_sleeps == 1 && ucx_noc_probe() == 1 && tr_wait[E_ID] == 4);
		phases(1);
		return 1;
	}
	return 0;
}

static void test_e_one_iteration_per_phase(void)
{
	setup(0, 1, 4);
	host_set_current(H_ID);
	CHECK(ucx_noc_comm_create(PORT_H) == UCX_NOC_OK);
	host_set_current(I_ID);
	CHECK(ucx_noc_comm_create(PORT_I) == UCX_NOC_OK);

	host_set_current(E_ID);
	CHECK(ucx_noc_comm_create(PORT_E) == UCX_NOC_OK);
	deliver(CPU_C, PORT_C, PORT_E, COMM_CE_WORKLOAD);
	deliver(CPU_C, PORT_C, PORT_E, COMM_CE_WORKLOAD);
	/* task_e opens its port again: the driver keeps the queue of the slot */
	e_blocks = 0;
	host_on_block = e_block;
	if (!setjmp(host_leave))
		task_e();

	CHECK(e_blocks == 3);
	CHECK(host_sleeps == 2);
	CHECK(host_sleep_phase[0] == 3 && host_sleep_phase[1] == 4);
	const uint32_t m[] = {ITER_MARK('E', 1), ITER_MARK_END | ITER_MARK('E', 1),
	                      ITER_MARK('E', 2), ITER_MARK_END | ITER_MARK('E', 2)};
	CHECK(marks_are(m, 4));
	for (int i = 0; i < host_yields && i < 16; i++)
		CHECK(!host_yield_irq[i]);              /* every block of E is a phase wait */
}

/* ------------------------------------------- 5. J: arrivals before its phase */

#define J_ID 1
#define G_ID 2

static int j_blocks;
static noc_packet_t *g_pkt;

static int j_block(void)
{
	j_blocks++;
	if (j_blocks == 1) {
		/* iteration 1 of G (phase 2), H and I (phase 3) arrive before phase 4 */
		CHECK(tr_wait[J_ID] == 4);
		phases(1);                              /* phase 2 */
		host_set_current(G_ID);
		ucx_noc_send(CPU_J, PORT_J, g_pkt, COMM_GJ_WORKLOAD);
		host_set_current(J_ID);
		phases(1);                              /* phase 3 */
		deliver(CPU_H, PORT_H, PORT_J, COMM_HJ_WORKLOAD);
		deliver(CPU_I, PORT_I, PORT_J, COMM_IJ_WORKLOAD);
		CHECK(host_task_state(J_ID) == TASK_BLOCKED);
		CHECK(host_sleeps == 0);
		phases(1);                              /* phase 4 */
		CHECK(host_task_state(J_ID) == TASK_READY);
		return 1;
	}
	return 0;
}

static void test_j_waits_for_its_phase(void)
{
	setup(1, 1, 3);                             /* node 3: IDLE, J, G */
	host_set_current(G_ID);
	CHECK(ucx_noc_comm_create(PORT_G) == UCX_NOC_OK);
	g_pkt = create_pkt(COMM_GJ_WORKLOAD);
	host_set_current(J_ID);
	j_blocks = 0;
	host_on_block = j_block;
	phases(1);                                  /* phase 1: J waits for phase 1 + 3 */
	if (!setjmp(host_leave))
		task_j();
	CHECK(j_blocks == 2);
	CHECK(host_sleeps == 1 && host_sleep_phase[0] == 4);
	const uint32_t m[] = {ITER_MARK('J', 1), ITER_MARK_END | ITER_MARK('J', 1)};
	CHECK(marks_are(m, 2));
	ucx_free(g_pkt);
}

/* ------------------------------------------- 6. A: one iteration per release */

static int a_blocks;

static int a_block(void)
{
	a_blocks++;
	CHECK(host_sleeps == a_blocks - 1);         /* no iteration before its release */
	if (a_blocks > 3)
		return 0;
	phases(1);
	return 1;
}

static void test_a_released_by_the_tick(void)
{
	setup(0, 0, 5);                             /* node 0: IDLE, F, D, B, A */
	host_set_current(3);
	CHECK(ucx_noc_comm_create(PORT_B) == UCX_NOC_OK);
	host_set_current(4);
	a_blocks = 0;
	host_on_block = a_block;
	if (!setjmp(host_leave))
		task_a();
	CHECK(a_blocks == 4 && host_sleeps == 3);
	CHECK(host_sleep_phase[0] == 1 && host_sleep_phase[1] == 2 && host_sleep_phase[2] == 3);
	host_set_current(3);
	CHECK(ucx_noc_probe() == 3);                /* one packet of A to B per iteration */
}

int main(void)
{
	RUN_FORK(test_tick_hook);
	RUN_FORK(test_phase_wait);
	RUN_FORK(test_arrival_does_not_wake_a_phase_wait);
	RUN_FORK(test_e_one_iteration_per_phase);
	RUN_FORK(test_j_waits_for_its_phase);
	RUN_FORK(test_a_released_by_the_tick);
	DONE();
}
