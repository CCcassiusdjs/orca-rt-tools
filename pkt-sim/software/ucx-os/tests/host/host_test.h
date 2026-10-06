#ifndef HOST_TEST_H
#define HOST_TEST_H
#include <stdio.h>
#include <stdlib.h>

extern int host_live_blocks, host_fail_next_malloc, host_irq_enabled;
extern uint32_t host_counter3, host_counter4, host_ddma_regs[16];
extern uint16_t host_current_task;
void host_arena_init(void);
void host_tasks_init(int n);
uint8_t host_task_state(int id);
void host_ddma_map(uint32_t dimx, uint32_t dimy, uint32_t x, uint32_t y);

static int host_failures = 0;
#define CHECK(cond) do { if (!(cond)) { host_failures++; \
	fprintf(stderr, "  check failed %s:%d: %s\n", __FILE__, __LINE__, #cond); } } while (0)
#define RUN(t) do { int f0 = host_failures; t(); \
	printf("%s %s\n", host_failures == f0 ? "PASS" : "FAIL", #t); fflush(stdout); } while (0)
#define DONE() return host_failures ? 1 : 0
#endif
