/* file:          tick_release.c
 * description:   release by tick of the phase model of the analysis flow
 *
 * The phase model (paper, Section 6.3; orca-rt-tools, rttools/bench_t/
 * estimate.py) runs each task v at most once per phase and serves
 * iteration j in phase j + n(v), where n(v) is the phase index of v and
 * phase j starts at the tick after release j. This module gives the
 * platform that rule (-DUCX_TICK_RELEASE; Makefile, TR_DEFS):
 *
 * | Element | Rule |
 * |---|---|
 * | Release interrupt (irq4_handler) | the release generator of manycore_pe.sv fires on every PE with a task (RELEASE_MASK); the handler counts it |
 * | Tick hook (ucx_app_tick, kernel/sched.c dispatch, -DUCX_APP_TICK) | before the scheduler of the tick: the phase index grows by the counted releases, and every task that waits for a phase at or below it becomes ready |
 * | ucx_phase_wait(p) | the task blocks until the phase index reaches max(p, phase of its previous start + 1); a task calls it with p = j + n(v) before it reads the input of iteration j (FIFO) |
 * | Packet arrival (lib/noc.c, enable_receiver) | does not wake a task that waits for a phase; the tick hook wakes it |
 *
 * The check and the block run with interrupts disabled, so a tick between
 * them does not lose the wake-up; yield keeps the interrupt state of its
 * caller across the switch (kernel/sched.c, UCX_TICK_RELEASE). Without
 * UCX_TICK_RELEASE the file defines nothing and the image does not change.
 */

#include <ucx.h>
#include <lib/tick_release.h>

#ifdef UCX_TICK_RELEASE

static volatile uint32_t tr_pending = 0;   /* release interrupts not applied yet */
static volatile uint32_t tr_phase = 0;     /* phase index of this PE */
static uint32_t tr_wait[MAX_TASKS];        /* phase a blocked task waits for (0: none) */
static uint32_t tr_last[MAX_TASKS];        /* phase of the previous start of each task */
#ifdef UCX_NOC_TT
static uint32_t tr_phase_tick = 0;         /* tick (lib/noc_tt.c) at which tr_phase took its value */
static uint32_t tr_tick[MAX_TASKS];        /* tick of the phase of the current job of each task */
#endif

/* release interrupt (manycore_pe.sv, wake-up generator); interrupts stay
 * disabled until the return of _isr (kernel/sched.c, UCX_ISR_NESTING) */
void irq4_handler(void)
{
#ifdef UCX_ISR_NESTING
	_di();
#endif
	tr_pending++;

	/* flag interruption down */
	volatile int *irq_flag_down = (volatile int *)(0x2000004C);
	*irq_flag_down = !(*irq_flag_down);
#ifdef UCX_ISR_NESTING
	_ei();
#endif
}

/* tick hook (kernel/sched.c, dispatch): applies the releases since the
 * previous tick and readies the tasks whose phase has come */
void ucx_app_tick(void)
{
	struct tcb_s *p;

#ifdef UCX_NOC_TT
	/* the release generator raises its request before the tick of its
	 * phase, and the link schedule keeps any handler that runs at the
	 * request from reaching the tick (premise (ii) of the analysis); a
	 * request pending here is served first */
	if (IRQ_CAUSE & MASK_IRQ4)
		irq4_handler();
#endif
	if (!tr_pending)
		return;
	tr_phase += tr_pending;
	tr_pending = 0;
#ifdef UCX_NOC_TT
	tr_phase_tick = ucx_noc_tt_ticks();
#endif

	p = kcb_p->tcb_first;
	do {
		uint32_t w = tr_wait[p->id];

		if (w && w <= tr_phase && p->state == TASK_BLOCKED)
			p->state = TASK_READY;
		p = p->tcb_next;
	} while (p != kcb_p->tcb_first);
}

uint32_t ucx_phase(void)
{
	return tr_phase;
}

#ifdef UCX_NOC_TT
/* tick of the phase of the current job of the calling task, recorded by
 * ucx_phase_wait with interrupts disabled (a tick between the reads of
 * tr_phase and tr_phase_tick cannot mix two phases) */
uint32_t ucx_job_tick(void)
{
	return tr_tick[ucx_task_id()];
}
#endif

int ucx_phase_waiting(uint16_t task_id)
{
	return task_id < MAX_TASKS && tr_wait[task_id] != 0;
}

uint32_t ucx_phase_wait(uint32_t phase)
{
	uint16_t id = ucx_task_id();
	uint32_t want = phase > tr_last[id] ? phase : tr_last[id] + 1;
	uint32_t now;

	_di();
	while (tr_phase < want) {
		tr_wait[id] = want;
		kcb_p->tcb_p->state = TASK_BLOCKED;
		ucx_task_yield();
		_di();
	}
	tr_wait[id] = 0;
	tr_last[id] = tr_phase;
#ifdef UCX_NOC_TT
	tr_tick[id] = tr_phase_tick;
#endif
	now = tr_phase;
	_ei();

	return now;
}

#endif
