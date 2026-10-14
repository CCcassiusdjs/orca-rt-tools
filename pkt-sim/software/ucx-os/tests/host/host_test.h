#ifndef HOST_TEST_H
#define HOST_TEST_H
#include <stdio.h>
#include <stdlib.h>

extern int host_live_blocks, host_fail_next_malloc, host_irq_enabled, host_isr_nested;
extern uint32_t host_counter3, host_counter4, host_ddma_regs[16];
extern uint16_t host_current_task;
#define HOST_ITER_MARKS 64
extern uint32_t host_iter_marks[HOST_ITER_MARKS];
extern int host_iter_nmarks;
void host_arena_init(void);
void host_tasks_init(int n);
uint8_t host_task_state(int id);
void host_set_current(int id);
void host_ddma_map(uint32_t dimx, uint32_t dimy, uint32_t x, uint32_t y);
void host_isr(void (*handler)(void));

static int host_failures = 0;
#define CHECK(cond) do { if (!(cond)) { host_failures++; \
	fprintf(stderr, "  check failed %s:%d: %s\n", __FILE__, __LINE__, #cond); } } while (0)
#define RUN(t) do { int f0 = host_failures; t(); \
	printf("%s %s\n", host_failures == f0 ? "PASS" : "FAIL", #t); fflush(stdout); } while (0)
#define DONE() return host_failures ? 1 : 0

/* runs the test in a child process: a memory error (ASan)
 * brings down only that test */
#include <unistd.h>
#include <sys/wait.h>
#define RUN_FORK(t) do { fflush(stdout); fflush(stderr); pid_t pid = fork(); \
	if (pid == 0) { t(); fflush(stdout); _exit(host_failures ? 1 : 0); } \
	int st = 0; waitpid(pid, &st, 0); \
	int ok = WIFEXITED(st) && WEXITSTATUS(st) == 0; \
	if (!ok) host_failures++; \
	printf("%s %s\n", ok ? "PASS" : (WIFEXITED(st) && WEXITSTATUS(st) == 1 ? "FAIL" : "CRASH"), #t); \
	fflush(stdout); } while (0)
#endif
