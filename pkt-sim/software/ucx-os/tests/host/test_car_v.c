/* Generated application CAR-V (app/car_v.c, rttools.ucxgen) with lib/noc.c.
 *
 * Iteration markers: a task writes ITER_BEGIN(letter, k) when it has the
 * input of iteration k and ITER_END(letter, k) after its last send (after
 * the work for a task without output edge), also for the two iterations
 * of one run; the letter of the task is the field `letter` of TASKS
 * (iter_letter of car_v.json).
 *
 * The task runs until it blocks; then ucx_task_yield() delivers the next
 * batch of packets (or the release) or leaves the task with longjmp. */
#include <ucx.h>
#include "host_test.h"

#define TASK_STOPPED 0
#define DEFAULT_STACK_SIZE 2048

void irq3_handler(void);

static jmp_buf host_leave;
static int (*host_on_block)(void);   /* 0: leave the task */
static int host_sleeps;
static int32_t host_sleep_cycles[16];

void ucx_task_yield(void)
{
	if (!host_on_block || !host_on_block())
		longjmp(host_leave, 1);
}

void ucx_sleep(int32_t cycles)
{
	if (host_sleeps < 16)
		host_sleep_cycles[host_sleeps] = cycles;
	host_sleeps++;
}

int32_t ucx_task_add(void *task, char *name, uint16_t stack_size, uint16_t period,
	uint16_t capacity, uint16_t deadline)
{
	return 0;
}

#include "../../app/car_v.c"

static const struct task_s *task(const char *name)
{
	for (int i = 0; i < N_TASKS; i++)
		if (!strcmp(TASKS[i].name, name))
			return &TASKS[i];
	return NULL;
}

static void setup(uint32_t x, uint32_t y, int tasks)
{
	host_arena_init();
	host_ddma_map(4, 4, x, y);
	host_tasks_init(tasks);
	noc_driver_init();
	host_irq_enabled = 1;
	host_on_block = NULL;
	host_sleeps = 0;
	host_iter_nmarks = 0;
}

static int marks_are(const uint32_t *expected, int n)
{
	if (host_iter_nmarks != n)
		return 0;
	for (int i = 0; i < n; i++)
		if (host_iter_marks[i] != expected[i])
			return 0;
	return 1;
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

/* ------------------------------------------- OBMG (no output edge) */

static int obmg_batches;
static const struct task_s *stph, *obmg;

/* the packets of STPH of iterations 1 and 2 wait in the queue: one run
 * of OBMG serves both */
static int obmg_block(void)
{
	if (obmg_batches++ > 0)
		return 0;
	deliver(12, stph->port, obmg->port, TAG(stph->out[0].flow, 1));
	deliver(12, stph->port, obmg->port, TAG(stph->out[0].flow, 2));
	return 1;
}

static void test_sink_marks_each_iteration_of_a_run(void)
{
	stph = task("STPH");
	obmg = task("OBMG");
	CHECK(stph && obmg);
	if (!stph || !obmg)
		return;
	setup(3, 3, 2);                             /* node 15: IDLE, OBMG */
	CHECK(ucx_noc_cpu_id() == 15);
	host_current_task = 1;
	obmg_batches = 0;
	host_on_block = obmg_block;
	if (!setjmp(host_leave))
		task_OBMG();

	CHECK(host_sleeps == 2);
	CHECK(host_sleep_cycles[0] == obmg->workload && host_sleep_cycles[1] == obmg->workload);
	CHECK(obmg_batches == 2);                   /* one block after the two iterations */
	const uint32_t m[] = {ITER_MARK(obmg->letter, 1), ITER_MARK_END | ITER_MARK(obmg->letter, 1),
	                      ITER_MARK(obmg->letter, 2), ITER_MARK_END | ITER_MARK(obmg->letter, 2)};
	CHECK(marks_are(m, 4));
	CHECK(obmg->letter == 'W');
}

/* ------------------------------------------- FBU4 (source) */

static int fbu4_releases;

static int fbu4_block(void)
{
	return fbu4_releases++ < 2;                 /* two releases, then leave */
}

/* the source marks the begin after the release and the end after its
 * send (tag of iteration k); BFE4 is on the same node (local queue) */
static void test_source_marks_after_release_and_send(void)
{
	const struct task_s *fbu4 = task("FBU4"), *bfe4 = task("BFE4");
	CHECK(fbu4 && bfe4);
	if (!fbu4 || !bfe4)
		return;
	setup(1, 0, 3);                             /* node 1: IDLE, FBU4, BFE4 */
	CHECK(ucx_noc_cpu_id() == 1);
	host_current_task = 2;
	CHECK(ucx_noc_comm_create(bfe4->port) == UCX_NOC_OK);
	host_current_task = 1;
	fbu4_releases = 0;
	host_on_block = fbu4_block;
	if (!setjmp(host_leave))
		task_FBU4();

	CHECK(host_sleeps == 2);
	CHECK(host_counter3 == TAG(fbu4->out[0].flow, 2));
	const uint32_t m[] = {ITER_MARK(fbu4->letter, 1), ITER_MARK_END | ITER_MARK(fbu4->letter, 1),
	                      ITER_MARK(fbu4->letter, 2), ITER_MARK_END | ITER_MARK(fbu4->letter, 2)};
	CHECK(marks_are(m, 4));
	host_current_task = 2;
	CHECK(ucx_noc_probe() == 2);                /* both packets in the queue of BFE4 */
}

int main(void)
{
	RUN_FORK(test_sink_marks_each_iteration_of_a_run);
	RUN_FORK(test_source_marks_after_release_and_send);
	DONE();
}
