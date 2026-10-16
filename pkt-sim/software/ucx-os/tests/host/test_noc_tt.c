/* Time-triggered injection of lib/noc_tt.c (-DUCX_NOC_TT).
 *
 * 1. ucx_noc_send_at keeps a packet for another PE until its instant: the
 *    tick routine of the tick of the instant arms the compare register of
 *    TIMER1 with the step of the instant; the compare interrupt at that
 *    step injects the packet (target, size, address and command of the
 *    DDMA; target node, port and tag written into the packet) and masks the
 *    compare interrupt when no packet remains for the tick.
 * 2. The queue keeps the order of the instants, not the order of the calls.
 * 3. A packet whose instant is step 0 of a tick, or a tick that passed,
 *    leaves at the tick routine.
 * 4. The DDMA in its handshake state (0x40) after the previous packet gets
 *    the send command 0 before the next injection; a DDMA that sends keeps
 *    the packet in the queue.
 * 5. A packet for a task of the same PE goes to its queue at once.
 * 6. The queue holds NOC_TT_SLOTS packets; one more returns
 *    UCX_NOC_OUT_OF_MEMORY. ucx_noc_send_at returns 0 when the kernel keeps
 *    the packet and leaves interrupts enabled. */
#include <ucx.h>
#include "host_test.h"

void timer1ocr_handler(void);

#define NODE 1                     /* 2x2 mesh, node (1,0) */
#define ST_IDLE (0x01 << 8)        /* DDMA_STATUS: send state in bits 15:8 */
#define ST_HANDSHAKE (0x40 << 8)
#define ST_SENDING (0x10 << 8)

static noc_packet_t *pkts[10];

static void setup(void)
{
	host_arena_init();
	host_ddma_map(2, 2, 1, 0);
	host_tasks_init(4);
	noc_driver_init();
	host_irq_enabled = 1;
	host_ddma_regs[5] = ST_IDLE;
	host_timer1 = 0;
	host_timer1ocr = 0;
	host_timercauseinv = 0;
	host_timermask = 0x04;         /* tick (TIMER1 CTC) */
	for (int i = 0; i < 10; i++)
		pkts[i] = ucx_noc_create_packet(8);
}

/* tick: TIMER1 restarts at step 0 */
static void tick(void)
{
	host_timer1 = 0;
	host_isr(ucx_noc_tt_tick);
}

/* TIMER1 reaches `step`; the compare interrupt runs when it is armed and due */
static void step_to(uint32_t step)
{
	host_timer1 = step;
	if ((host_timermask & MASK_TIMER1OCR) && host_timer1 >= host_timer1ocr)
		host_isr(timer1ocr_handler);
}

static int injected(noc_packet_t *p)
{
	return host_ddma_regs[4] == 1 && host_ddma_regs[2] == (uint32_t)(uintptr_t)p;
}

static void test_inject_at_instant(void)                 /* 1 */
{
	setup();
	struct ucx_tt_at at = {1, 100};
	uint32_t t0 = ucx_noc_tt_ticks();
	CHECK(ucx_noc_send_at(3, 7, pkts[0], 33, t0, &at) == 0);
	CHECK(host_irq_enabled == 1);
	CHECK(host_counter3 == 33);
	CHECK(ucx_noc_tt_pending() == 1);
	CHECK(host_ddma_regs[4] == 0);
	CHECK(!(host_timermask & MASK_TIMER1OCR));      /* instant in the next tick */
	tick();
	CHECK(host_timer1ocr == 100);
	CHECK(host_timermask & MASK_TIMER1OCR);
	CHECK(host_timercauseinv & MASK_TIMER1OCR);
	CHECK(host_ddma_regs[4] == 0);
	step_to(99);
	CHECK(host_ddma_regs[4] == 0);
	step_to(100);
	CHECK(injected(pkts[0]));
	CHECK(host_ddma_regs[1] == ((1u << 8) | 1u));   /* node 3 of the 2x2 mesh: x 1, y 1 */
	CHECK(host_ddma_regs[3] == (sizeof(noc_packet_t) + 8 + 3) / 4);
	CHECK(pkts[0]->target_node == 3 && pkts[0]->target_port == 7 && pkts[0]->tag == 33);
	CHECK(ucx_noc_tt_pending() == 0);
	CHECK(!(host_timermask & MASK_TIMER1OCR));
}

static void test_order_of_instants(void)                 /* 2 */
{
	setup();
	struct ucx_tt_at late = {0, 500}, early = {0, 200};
	uint32_t t0 = ucx_noc_tt_ticks();
	CHECK(ucx_noc_send_at(2, 1, pkts[1], 11, t0 + 1, &late) == 0);
	CHECK(ucx_noc_send_at(3, 1, pkts[2], 12, t0 + 1, &early) == 0);
	tick();
	CHECK(host_timer1ocr == 200);
	step_to(200);
	CHECK(injected(pkts[2]));
	CHECK(host_timer1ocr == 500 && (host_timermask & MASK_TIMER1OCR));
	host_ddma_regs[5] = ST_HANDSHAKE;
	step_to(500);
	CHECK(injected(pkts[1]));
	CHECK(ucx_noc_tt_pending() == 0);
}

static void test_step_zero_and_late(void)                /* 3 */
{
	setup();
	struct ucx_tt_at zero = {2, 0}, past = {0, 9};
	uint32_t t0 = ucx_noc_tt_ticks();
	CHECK(ucx_noc_send_at(3, 1, pkts[3], 13, t0, &zero) == 0);
	tick();
	CHECK(host_ddma_regs[4] == 0);
	tick();                                          /* tick t0 + 2, step 0 */
	CHECK(injected(pkts[3]));
	/* instant in a tick that passed: the next tick routine injects it */
	host_ddma_regs[4] = 0;
	CHECK(ucx_noc_send_at(3, 1, pkts[4], 14, ucx_noc_tt_ticks() - 2, &past) == 0);
	CHECK(injected(pkts[4]));                        /* tt_insert: the instant passed */
	CHECK(ucx_noc_tt_pending() == 0);
}

static void test_handshake_and_busy(void)                /* 4 */
{
	setup();
	struct ucx_tt_at at = {0, 50};
	uint32_t t0 = ucx_noc_tt_ticks();
	CHECK(ucx_noc_send_at(3, 1, pkts[5], 15, t0 + 1, &at) == 0);
	tick();
	host_ddma_regs[5] = ST_SENDING;
	step_to(50);
	CHECK(host_ddma_regs[4] == 0 && ucx_noc_tt_pending() == 1);
	CHECK(host_timermask & MASK_TIMER1OCR);          /* armed again */
	host_ddma_regs[4] = 1;                           /* command of the previous packet */
	host_ddma_regs[5] = ST_HANDSHAKE;
	step_to(51);
	CHECK(injected(pkts[5]) && ucx_noc_tt_pending() == 0);
}

static void test_local_target(void)                      /* 5 */
{
	setup();
	host_current_task = 1;
	CHECK(ucx_noc_comm_create(5) == UCX_NOC_OK);
	struct ucx_tt_at at = {3, 3};
	CHECK(ucx_noc_send_at(NODE, 5, pkts[6], 16, ucx_noc_tt_ticks(), &at) == 0);
	CHECK(ucx_noc_tt_pending() == 0);
	CHECK(ucx_noc_probe() == 1);
	CHECK(host_ddma_regs[4] == 0);
}

static void test_queue_full(void)                        /* 6 */
{
	setup();
	struct ucx_tt_at at = {5, 1};
	uint32_t t0 = ucx_noc_tt_ticks();
	for (int i = 0; i < 8; i++)
		CHECK(ucx_noc_send_at(3, 1, pkts[i], 20 + i, t0, &at) == 0);
	CHECK(ucx_noc_tt_pending() == 8);
	CHECK(ucx_noc_send_at(3, 1, pkts[8], 28, t0, &at) == UCX_NOC_OUT_OF_MEMORY);
	CHECK(host_irq_enabled == 1);
	CHECK(ucx_noc_tt_pending() == 8);
}

int main(void)
{
	RUN_FORK(test_inject_at_instant);
	RUN_FORK(test_order_of_instants);
	RUN_FORK(test_step_zero_and_late);
	RUN_FORK(test_handshake_and_busy);
	RUN_FORK(test_local_target);
	RUN_FORK(test_queue_full);
	DONE();
}
