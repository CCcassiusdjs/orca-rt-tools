/* file:          noc_tt.c
 * description:   time-triggered injection of the packets between PEs
 *
 * The link schedule of the analysis flow (AGS, orca-rt-tools
 * rttools/modules/backend/ags) gives each packet between PEs an injection
 * instant s_{i,j}, in cycles from the start of the phase of the job that
 * sends it. This module injects each packet at that instant
 * (-DUCX_NOC_TT; Makefile, TR_DEFS and TT_DEFS):
 *
 * | Element | Rule |
 * |---|---|
 * | ucx_noc_send_at | the job hands the packet and its instant (table app/<app>_tt.h of rttools.ucxgen tt) to the kernel, which keeps it in a queue in the order of the instants (NOC_TT_SLOTS entries); a packet to a task of the same PE goes to the queue of the task at once (ucx_noc_send) |
 * | Tick routine (ucx_noc_tt_tick, kernel/sched.c dispatch) | counts the tick; injects the first packet of the queue when its instant is this tick at step 0 or has passed; programs the compare register of TIMER1 (TIMER1OCR) with the step of the first packet when its instant falls in this tick |
 * | Compare interrupt (timer1ocr_handler, irq0_handler of arch/riscv/hf-riscv-e/interrupt.c) | TIMER1 reached the step: injects the first packet and programs the step of the next packet of this tick, or masks the compare interrupt |
 * | End of a send | irq1 stays masked (lib/noc.c, noc_driver_init); the next injection writes 0 to the send command when the DDMA waits in its handshake state after the previous packet of this PE |
 *
 * TIMER1 counts one step per 16 cycles from 0 at the tick (hal.c), so the
 * compare interrupt comes 16 TIMER1OCR cycles after the tick. The table
 * holds the instant s rounded up to a multiple of 16 cycles: the injection
 * never precedes s. The compare cause of hw/peripherals/
 * peripherals_minimal.vhd is TIMER1 < TIMER1OCR; with its bit of
 * TIMERCAUSEINV at 1 the interrupt stays pending from step TIMER1OCR to the
 * end of the tick, and the tick routine of the next tick injects a packet
 * whose instant passed. The job converts the target and the size for the
 * DDMA (_ddma_dest_xy, _ddma_flits) before it disables interrupts, so the
 * handlers only write the registers of the DDMA. The queue, the timer
 * registers and the DDMA are written with interrupts disabled (handlers,
 * and tt_insert between _di and _ei). Without UCX_NOC_TT the file defines
 * nothing and the image does not change.
 */

#include <ucx.h>

#ifdef UCX_NOC_TT

/* entries of the queue of injections of one PE (a power of 2);
 * rttools.ucxgen tt checks that the link schedule of each PE needs at most
 * this number */
#ifndef NOC_TT_SLOTS
#define NOC_TT_SLOTS 8
#endif
#define TT_MASK (NOC_TT_SLOTS - 1)

/* states of the send state machine of the DDMA (hw/ddma/ddma.sv,
 * send_state_t), read by _ddma_send_status */
#define TT_DDMA_IDLE		0x01
#define TT_DDMA_HANDSHAKE	0x40

struct tt_entry_s {
	uint32_t tick;			/* tick of the instant */
	uint16_t count;			/* step of TIMER1 in that tick */
	uint16_t tag;
	uint16_t target_cpu;
	uint16_t target_port;
	uint32_t xy;			/* DDMA_SEND_DEST_IN of the target */
	uint32_t flits;			/* DDMA_SEND_SIZE_IN of the packet */
	noc_packet_t *pkt;
};

/* ring of the pending injections in the order of their instants: entry i
 * of the queue is tt_queue[(tt_head + i) & TT_MASK] */
static struct tt_entry_s tt_queue[NOC_TT_SLOTS];
static volatile uint32_t tt_head = 0;
static volatile uint32_t tt_count = 0;
static volatile uint32_t tt_tick = 0;		/* index of the current tick */

uint32_t ucx_noc_tt_ticks(void)
{
	return tt_tick;
}

uint32_t ucx_noc_tt_pending(void)
{
	return tt_count;
}

/* injects packet `e` when the DDMA is idle or waits in its handshake
 * state after the previous packet; returns 0 while the DDMA sends */
static int tt_inject(struct tt_entry_s *e)
{
	noc_packet_t *pkt = e->pkt;
	uint8_t st = _ddma_send_status();

	if (st != TT_DDMA_IDLE) {
		if (st != TT_DDMA_HANDSHAKE)
			return 0;
		/* the DDMA leaves the handshake state at the next cycle; the
		 * stores of _ddma_send_xy below come after it */
		_ddma_send_ack();
	}
	pkt->target_node = e->target_cpu;
	pkt->target_port = e->target_port;
	pkt->tag = e->tag;
	_ddma_send_xy(e->xy, e->flits, (uint32_t *)pkt);

	return 1;
}

/* injects the first packet when its instant has come (the current step
 * of this tick or before), then programs the compare interrupt for the
 * first packet of this tick, or masks it */
static void tt_arm(void)
{
	struct tt_entry_s *e = &tt_queue[tt_head];

	if (tt_count && (e->tick < tt_tick || (e->tick == tt_tick && e->count <= (TIMER1 & 0xffff)))
		&& tt_inject(e)) {
		tt_head = (tt_head + 1) & TT_MASK;
		tt_count--;
		e = &tt_queue[tt_head];
	}

	if (tt_count && e->tick <= tt_tick) {
		/* step 0: TIMER1 < 0 never holds, the interrupt is pending now */
		TIMER1OCR = e->tick < tt_tick ? 0 : e->count;
		TIMERCAUSEINV |= MASK_TIMER1OCR;
		TIMERMASK |= MASK_TIMER1OCR;
	} else {
		TIMERMASK &= ~MASK_TIMER1OCR;
	}
}

/* tick routine (kernel/sched.c, dispatch, interrupts disabled) */
void ucx_noc_tt_tick(void)
{
	tt_tick++;
	tt_arm();
}

/* compare interrupt of TIMER1 (irq0_handler, timer_vector[3]):
 * irq0_handler toggled the compare bit of TIMERCAUSEINV before the call;
 * tt_arm sets it again with the next step or masks the interrupt.
 * Interrupts stay disabled until the return of _isr (kernel/sched.c) */
void timer1ocr_handler(void)
{
	tt_arm();
}

/* inserts `e` after the entries with the same or an earlier instant;
 * interrupts disabled (ucx_noc_send_at); 0 when the queue is full */
static __attribute__((noinline)) uint32_t tt_insert(const struct tt_entry_s *e)
{
	uint32_t i;

	if (tt_count == NOC_TT_SLOTS)
		return 0;
	i = tt_count;
	while (i > 0) {
		struct tt_entry_s *p = &tt_queue[(tt_head + i - 1) & TT_MASK];

		if (p->tick < e->tick || (p->tick == e->tick && p->count <= e->count))
			break;
		tt_queue[(tt_head + i) & TT_MASK] = *p;
		i--;
	}
	tt_queue[(tt_head + i) & TT_MASK] = *e;
	tt_count++;
	if (i == 0)
		tt_arm();

	return 1;
}

uint32_t ucx_noc_send_at(uint16_t target_cpu, uint16_t target_port, noc_packet_t *pkt, uint16_t tag,
	uint32_t tick, const struct ucx_tt_at *at)
{
	struct tt_entry_s e;
	uint32_t ok;

	if (target_cpu == ucx_noc_cpu_id())
		return ucx_noc_send(target_cpu, target_port, pkt, tag);

#ifndef UCX_NO_INSTRUMENTATION
	set_counter_3(tag);
#endif
	e.tick = tick + at->ticks;
	e.count = at->count;
	e.tag = tag;
	e.target_cpu = target_cpu;
	e.target_port = target_port;
	e.xy = _ddma_dest_xy(target_cpu);
	e.flits = _ddma_flits(sizeof(noc_packet_t) + pkt->payload_size);
	e.pkt = pkt;

	_di();
	ok = tt_insert(&e);
	_ei();
	if (!ok) {
		printf("ucx_noc_send_at(): queue full, packet with tag %d dropped\n", tag);
		return UCX_NOC_OUT_OF_MEMORY;
	}

	return 0;
}

#endif
