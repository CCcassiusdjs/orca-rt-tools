/* Generated time-triggered application CAR-full (app/car_full.c,
 * rttools.ucxgen) with lib/noc.c built with -DUCX_NOC_LATEST (run.sh).
 *
 * 1. Tick hook: each release interrupt counts one phase (irq_pending); ucx_app_tick
 *    releases job j of task v at phase o_v + j k_v and readies a blocked
 *    task; two interrupts before one tick release both phases.
 * 2. Driver: the queue of a task keeps one packet per source (the newer
 *    packet replaces the queued one, which is freed) and an arrival does
 *    not wake the task.
 * 3. Job of NAVC (node 8): reads the latest packet of each input edge
 *    (job number in the first payload word), writes the begin marker, one
 *    read marker per input edge and the end marker, and sends on an edge
 *    with m_e = 5 only on jobs 1, 6, ...; the local packet to DIRC stays
 *    one entry of its queue with the newest job number. */
#include <ucx.h>
#include "host_test.h"

#define DEFAULT_STACK_SIZE 2048

void irq3_handler(void);

static jmp_buf host_leave;
static int (*host_on_block)(void);   /* 0: leave the task */
static int host_sleeps;

void ucx_task_yield(void)
{
	if (!host_on_block || !host_on_block())
		longjmp(host_leave, 1);
}

void ucx_sleep(int32_t cycles)
{
	host_sleeps++;
}

/* the kernel makes the new task the current one (kernel/ucx.c) */
static int host_added;
int32_t ucx_task_add(void *task, char *name, uint16_t stack_size, uint16_t period,
	uint16_t capacity, uint16_t deadline)
{
	if (host_added++)
		kcb_p->tcb_p = kcb_p->tcb_p->tcb_next;
	return host_added - 1;
}

#include "../../app/car_full.c"

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
	host_ddma_regs[5] = 0x100;                  /* DDMA send idle */
	host_tasks_init(tasks);
	noc_driver_init();
	host_irq_enabled = 1;
	host_on_block = NULL;
	host_sleeps = 0;
	host_iter_nmarks = 0;
	host_added = 0;
	n_local = 0;
	phase = 0;
	irq_pending = 0;
}

/* packet from another node with the job number `job` in its payload */
static noc_packet_t *deliver(uint16_t src_node, uint16_t src_port, uint16_t port, uint32_t job)
{
	host_ddma_regs[8] = 4;                      /* 4 flits = 16 bytes */
	irq2_handler();
	noc_packet_t *pkt = (noc_packet_t *)(uintptr_t)host_ddma_regs[6];
	CHECK(pkt != NULL);
	if (!pkt)
		return NULL;
	pkt->source_node = src_node;
	pkt->target_node = ucx_noc_cpu_id();
	pkt->source_port = src_port;
	pkt->target_port = port;
	pkt->payload_size = 4;
	pkt->tag = 0;
	memcpy(pkt->data, &job, 4);
	host_ddma_regs[7] = host_ddma_regs[6];      /* RECV_ADDR_OUT */
	irq3_handler();
	return pkt;
}

/* ------------------------------------------- 1. tick hook */

/* n release interrupts (irq4_handler counts them in irq_pending; its
 * acknowledge register does not exist on the host), then one tick */
static void phases(int n)
{
	irq_pending += n;
	ucx_app_tick();
}

static void test_tick_hook_releases_by_period(void)
{
	setup(0, 2, 4);                             /* node 8: IDLE, POSI, NAVC, DIRC */
	CHECK(ucx_noc_cpu_id() == 8);
	app_main();
	CHECK(n_local == 3);
	if (n_local != 3)
		return;
	CHECK(!strcmp(local_task[0]->name, "POSI") && !strcmp(local_task[1]->name, "NAVC")
	      && !strcmp(local_task[2]->name, "DIRC"));
	CHECK(local_task[0]->period == 25 && local_task[1]->period == 5 && local_task[2]->period == 5);
	CHECK(local_tcb[0]->id == 1 && local_tcb[2]->id == 3);
	for (int i = 0; i < 3; i++)
		local_tcb[i]->state = TASK_BLOCKED;
	phases(1);                                  /* phase 0: every task */
	CHECK(released[0] == 1 && released[1] == 1 && released[2] == 1);
	CHECK(local_tcb[0]->state == TASK_READY && local_tcb[1]->state == TASK_READY);
	for (int i = 0; i < 3; i++)
		local_tcb[i]->state = TASK_BLOCKED;
	phases(4);                                  /* phases 1 to 4: none */
	CHECK(released[0] == 1 && released[1] == 1 && released[2] == 1);
	CHECK(local_tcb[1]->state == TASK_BLOCKED);
	phases(1);                                  /* phase 5: NAVC and DIRC */
	CHECK(released[0] == 1 && released[1] == 2 && released[2] == 2);
	CHECK(local_tcb[0]->state == TASK_BLOCKED && local_tcb[1]->state == TASK_READY);
	ucx_app_tick();                             /* a tick without interrupt releases nothing */
	CHECK(phase == 6 && released[1] == 2);
	phases(20);                                 /* phases 6 to 25 at one tick */
	CHECK(phase == 26 && released[0] == 2 && released[1] == 6 && released[2] == 6);
}

/* ------------------------------------------- 2. driver */

static void test_latest_packet_per_source(void)
{
	setup(1, 0, 3);
	host_current_task = 1;
	CHECK(ucx_noc_comm_create(5) == UCX_NOC_OK);
	host_tasks_init(3);                         /* every task blocked */
	int live = host_live_blocks;
	deliver(0, 1, 5, 7);
	deliver(0, 1, 5, 8);                        /* same source: replaces job 7 */
	CHECK(ucx_noc_probe() == 1);
	CHECK(host_live_blocks == live + 1);        /* the packet of job 7 was freed */
	CHECK(host_task_state(1) == TASK_BLOCKED);  /* no wake */
	deliver(2, 1, 5, 3);                        /* another node */
	CHECK(ucx_noc_probe() == 2);
	noc_packet_t *p = ucx_noc_receive();
	uint32_t job;
	memcpy(&job, p->data, 4);
	CHECK(p->source_node == 0 && job == 8);
	ucx_free(p);
}

/* ------------------------------------------- 3. job of NAVC */

static const struct task_s *navc, *obdb, *spes, *dirc;
static int navc_blocks;

static int navc_block(void)
{
	navc_blocks++;
	if (navc_blocks == 1) {
		released[1] = 1;
		deliver(4, obdb->port, navc->port, 7);
		deliver(4, obdb->port, navc->port, 8);
		deliver(1, spes->port, navc->port, 3);
		return 1;
	}
	if (navc_blocks == 2) {
		released[1] = 2;
		return 1;
	}
	return 0;
}

static void test_navc_reads_latest_and_sends_every_m(void)
{
	navc = task("NAVC");
	obdb = task("OBDB");
	spes = task("SPES");
	dirc = task("DIRC");
	CHECK(navc && obdb && spes && dirc);
	if (!navc || !obdb || !spes || !dirc)
		return;
	setup(0, 2, 4);
	app_main();
	host_current_task = 3;                      /* DIRC: queue of the local edge */
	CHECK(ucx_noc_comm_create(dirc->port) == UCX_NOC_OK);
	host_current_task = 2;
	kcb_p->tcb_p = local_tcb[1];
	navc_blocks = 0;
	host_on_block = navc_block;
	if (!setjmp(host_leave))
		task_NAVC();

	CHECK(host_sleeps == 2);
	CHECK(navc_blocks == 3);
	/* inputs in flow order: POSI (no packet yet), OBDB, SPES, VOD1, VOD2 */
	CHECK(navc->n_in == 5 && navc->in_letter[1] == obdb->letter && navc->in_letter[2] == spes->letter);
	int n = 2 * (2 + navc->n_in);
	CHECK(host_iter_nmarks == n);
	if (host_iter_nmarks == n) {
		uint32_t want[2] = {0, 8};
		for (int j = 0; j < 2; j++) {
			const uint32_t *m = host_iter_marks + j * (2 + navc->n_in);
			CHECK(m[0] == ITER_MARK(navc->letter, j + 1));
			CHECK(m[1] == ITER_MARK(navc->in_letter[0], 0x800000u));
			CHECK(m[2] == ITER_MARK(obdb->letter, 0x800000u | want[1]));
			CHECK(m[3] == ITER_MARK(spes->letter, 0x800000u | 3));
			CHECK(m[1 + navc->n_in] == (ITER_MARK_END | ITER_MARK(navc->letter, j + 1)));
		}
	}
	/* NAVC->OBDB has m_e = 5: job 1 sends, job 2 does not; the last tag of
	 * the job 2 is the edge to THRC */
	int every5 = -1, thrc = -1;
	for (int o = 0; o < navc->n_out; o++) {
		if (navc->out[o].every == 5)
			every5 = o;
		if (navc->out[o].cpu == 2)
			thrc = o;
	}
	CHECK(every5 >= 0 && thrc >= 0);
	if (thrc >= 0)
		CHECK(host_counter3 == TAG(navc->out[thrc].flow, 2));
	/* the local edge to DIRC: one queued buffer with job 2 */
	host_current_task = 3;
	CHECK(ucx_noc_probe() == 1);
	noc_packet_t *p = ucx_noc_receive();
	uint32_t job;
	memcpy(&job, p->data, 4);
	CHECK(job == 2 && p->source_node == ucx_noc_cpu_id());
}

int main(void)
{
	RUN_FORK(test_tick_hook_releases_by_period);
	RUN_FORK(test_latest_packet_per_source);
	RUN_FORK(test_navc_reads_latest_and_sends_every_m);
	DONE();
}
