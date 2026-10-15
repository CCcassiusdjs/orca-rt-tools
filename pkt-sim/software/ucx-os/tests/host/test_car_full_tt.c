/* Tick hook of CAR-full with the time-triggered injection (app/car_full.c
 * and the table TT_TICK of app/car_full_tt.h, rttools.ucxgen) built with
 * -DUCX_NOC_LATEST -DUCX_NOC_TT -DF_CPU=477952000 (run.sh).
 *
 * 1. On every PE, at every phase of TT_TICK and for every state of the
 *    tasks of the PE and every task that holds the CPU: the hook releases
 *    the tasks of bits 2 + i, and the search of krnl_schedule
 *    (kernel/sched.c) then dispatches the first ready task from the
 *    position of bits 0-1 in the circular list (idle task, then the tasks
 *    in creation order); with position 0, the first ready task after the
 *    one that holds the CPU. The phases from TT_TICK_LOOP repeat.
 * 2. Run CF5 (PE 4: OBDB, USOS, OBMG): at the tick of phase 11, USOS holds
 *    the CPU (its job began in the rest of phase 10 after the early end of
 *    OBDB) and OBMG is ready; the search from the running task gives the
 *    tick to OBMG, the hook gives it to USOS, as the model. */
#include <ucx.h>
#include "host_test.h"

#define DEFAULT_STACK_SIZE 2048

void ucx_task_yield(void)
{
}

void ucx_sleep(int32_t cycles)
{
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

/* the search of krnl_schedule(0) (kernel/sched.c) */
static struct tcb_s *schedule(void)
{
	if (kcb_p->tcb_p->state == TASK_RUNNING)
		kcb_p->tcb_p->state = TASK_READY;
	struct tcb_s *current_task = kcb_p->tcb_p;
	do {
		kcb_p->tcb_p = kcb_p->tcb_p->tcb_next;
		if (kcb_p->tcb_p->id == current_task->id)
			break;
	} while (kcb_p->tcb_p->state != TASK_READY || kcb_p->tcb_p->id == 0);
	if (kcb_p->tcb_p->state != TASK_READY)
		kcb_p->tcb_p = kcb_p->tcb_first;
	kcb_p->tcb_p->state = TASK_RUNNING;
	return kcb_p->tcb_p;
}

/* PE `node` with its tasks after app_main; returns the number of tasks */
static int setup_node(int node)
{
	host_arena_init();
	host_ddma_map(4, 4, node % 4, node / 4);
	host_ddma_regs[5] = 0x100;                  /* DDMA send idle */
	host_tasks_init(MAX_LOCAL + 1);
	noc_driver_init();
	host_irq_enabled = 1;
	host_added = 0;
	n_local = 0;
	phase = 0;
	irq_pending = 0;
	tick_idx = 0;
	app_main();
	/* circular list of the tasks of the PE only (the kernel holds no other task) */
	struct tcb_s *last = n_local ? local_tcb[n_local - 1] : kcb_p->tcb_first;
	last->tcb_next = kcb_p->tcb_first;
	return n_local;
}

/* position (1..n, 0: idle) of the first ready task from position `from`
 * (from > 0) or after position `after` (from = 0), over positions 1..n */
static int first_ready(const int *ready, int n, int from, int after)
{
	for (int k = 0; k < n; k++) {
		int pos = from ? (from - 1 + k) % n + 1 : (after + k) % n + 1;
		if (ready[pos])
			return pos;
	}
	return 0;
}

/* ------------------------------------------- 1. every PE, phase and state */

static void test_tick_dispatches_the_position_of_the_model(void)
{
	int cases = 0;
	for (int node = 0; node < 16; node++) {
		int n = setup_node(node);
		CHECK(n >= 1 && n <= 3);
		for (int t = 0; t < TT_TICKS; t++) {
			uint8_t e = TT_TICK[node][t];
			for (int cur = 0; cur <= n; cur++) {
				for (int s = 0; s < (1 << n); s++) {
					int ready[MAX_LOCAL + 1] = {0};
					for (int i = 0; i < n; i++) {
						released[i] = 0;
						local_tcb[i]->state = (s >> i) & 1 ? TASK_READY : TASK_BLOCKED;
					}
					kcb_p->tcb_first->state = TASK_READY;
					if (cur) {
						local_tcb[cur - 1]->state = TASK_RUNNING;
						kcb_p->tcb_p = local_tcb[cur - 1];
					} else {
						kcb_p->tcb_first->state = TASK_RUNNING;
						kcb_p->tcb_p = kcb_p->tcb_first;
					}
					for (int i = 0; i < n; i++)
						ready[i + 1] = (s >> i) & 1 || (e >> (2 + i)) & 1 || cur == i + 1;
					tick_idx = t;
					irq_pending = 1;
					ucx_app_tick();
					for (int i = 0; i < n; i++)
						CHECK(released[i] == ((e >> (2 + i)) & 1u));
					CHECK(tick_idx == (t + 1 == TT_TICKS ? TT_TICK_LOOP : (uint32_t)t + 1));
					struct tcb_s *d = schedule();
					int want = first_ready(ready, n, e & 3, cur);
					CHECK(d == (want ? local_tcb[want - 1] : kcb_p->tcb_first));
					if (d != (want ? local_tcb[want - 1] : kcb_p->tcb_first))
						fprintf(stderr, "  node %d tick %d cur %d states %d: dispatched %d, model %d\n",
							node, t, cur, s, d->id, want);
					cases++;
				}
			}
		}
	}
	CHECK(cases > 16 * TT_TICKS);
}

/* ------------------------------------------- 2. run CF5, PE 4, phase 11 */

static void test_usos_gets_the_tick_of_phase_11(void)
{
	CHECK(setup_node(4) == 3);
	CHECK(!strcmp(local_task[0]->name, "OBDB") && !strcmp(local_task[1]->name, "USOS")
	      && !strcmp(local_task[2]->name, "OBMG"));
	CHECK((TT_TICK[4][11] & 3) == 2 && (TT_TICK[4][11] >> 2) == 0);
	for (int with_table = 0; with_table < 2; with_table++) {
		local_tcb[0]->state = TASK_BLOCKED;     /* OBDB: job ended in phase 10 */
		local_tcb[1]->state = TASK_RUNNING;     /* USOS: job begun in the rest of phase 10 */
		local_tcb[2]->state = TASK_READY;       /* OBMG */
		kcb_p->tcb_p = local_tcb[1];
		if (with_table) {
			tick_idx = 11;
			irq_pending = 1;
			ucx_app_tick();
		}
		struct tcb_s *d = schedule();
		CHECK(d == local_tcb[with_table ? 1 : 2]);
	}
}

int main(void)
{
	RUN_FORK(test_tick_dispatches_the_position_of_the_model);
	RUN_FORK(test_usos_gets_the_tick_of_phase_11);
	DONE();
}
