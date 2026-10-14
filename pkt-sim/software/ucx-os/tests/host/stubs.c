/* Host stubs for the tests of lib/noc.c and device/ddma.c.
 *
 * The driver converts pointers to uint32_t (32-bit registers of the
 * DDMA). On the 64-bit host, the libc heap lies above 4 GiB; for
 * this reason ucx_malloc uses a static arena (non-PIE executable, low
 * address). Each freed block stays poisoned for AddressSanitizer,
 * which reports use after free. */
#include <ucx.h>
#include <string.h>
#include <sanitizer/asan_interface.h>
#include "host_test.h"

#define ARENA_BYTES (1u << 20)
#define REDZONE 32
static uint8_t arena[ARENA_BYTES] __attribute__((aligned(16)));
static uint32_t arena_top = REDZONE;

int host_live_blocks = 0;
int host_fail_next_malloc = 0;
volatile uint32_t host_irq_mask = 0;
int host_irq_enabled = 1;
uint32_t host_counter3 = 0, host_counter4 = 0;
uint16_t host_current_task = 0;

static struct tcb_s tcbs[MAX_TASKS];
static struct kcb_s kcb;
struct kcb_s *kcb_p = &kcb;

void host_arena_init(void)
{
	ASAN_POISON_MEMORY_REGION(arena, sizeof(arena));
}

void *ucx_malloc(uint32_t size)
{
	if (host_fail_next_malloc) {
		host_fail_next_malloc = 0;
		return NULL;
	}
	uint32_t sz = (size + 15u) & ~15u;
	if (arena_top + sz + REDZONE > ARENA_BYTES)
		return NULL;
	uint8_t *p = arena + arena_top;
	arena_top += sz + REDZONE;
	ASAN_UNPOISON_MEMORY_REGION(p, size ? size : 1);
	memset(p, 0, size);
	host_live_blocks++;
	return p;
}

void ucx_free(void *ptr)
{
	if (!ptr)
		return;
	if ((uint8_t *)ptr < arena || (uint8_t *)ptr >= arena + ARENA_BYTES) {
		fprintf(stderr, "ucx_free: pointer %p outside heap\n", ptr);
		__builtin_trap();
	}
	/* poisons up to the next redzone: the exact size is not stored */
	uint8_t *p = ptr;
	size_t n = 0;
	while (p + n < arena + arena_top && !__asan_address_is_poisoned(p + n))
		n++;
	ASAN_POISON_MEMORY_REGION(p, n);
	host_live_blocks--;
}

void _di(void) { host_irq_enabled = 0; }
void _ei(void) { host_irq_enabled = 1; }
void set_counter_3(uint32_t v) { host_counter3 = v; }
void set_counter_4(uint32_t v) { host_counter4 = v; }
/* iteration markers (device/cacc.c), in the order of the writes */
uint32_t host_iter_marks[HOST_ITER_MARKS];
int host_iter_nmarks = 0;
void set_iter_mark(uint32_t v)
{
	if (host_iter_nmarks < HOST_ITER_MARKS)
		host_iter_marks[host_iter_nmarks] = v;
	host_iter_nmarks++;
}
uint16_t ucx_task_id(void) { return host_current_task; }

/* circular list of TCBs with ids 0..n-1, as the kernel builds it */
void host_tasks_init(int n)
{
	for (int i = 0; i < n; i++) {
		tcbs[i].id = i;
		tcbs[i].state = TASK_BLOCKED;
		tcbs[i].tcb_next = &tcbs[(i + 1) % n];
	}
	kcb.tcb_p = &tcbs[0];
	kcb.tcb_first = &tcbs[0];
}

uint8_t host_task_state(int id) { return tcbs[id].state; }

/* task `id` runs: ucx_task_id() and kcb_p->tcb_p */
void host_set_current(int id)
{
	host_current_task = id;
	kcb.tcb_p = &tcbs[id];
}

/* DDMA registers (0x20000000 + 4*i) */
uint32_t host_ddma_regs[16];
extern volatile uint32_t *DDMA_NODE_ADDR, *DDMA_SEND_DEST_IN, *DDMA_SEND_ADDR_IN,
	*DDMA_SEND_SIZE_IN, *DDMA_SEND_CMD_IN, *DDMA_STATUS, *DDMA_RECV_ADDR_IN,
	*DDMA_RECV_ADDR_OUT, *DDMA_RECV_SIZE_OUT, *DDMA_RECV_CMD_IN;

void host_ddma_map(uint32_t dimx, uint32_t dimy, uint32_t x, uint32_t y)
{
	memset(host_ddma_regs, 0, sizeof(host_ddma_regs));
	host_ddma_regs[0] = (dimx << 24) | (dimy << 16) | (x << 8) | y;
	DDMA_NODE_ADDR     = &host_ddma_regs[0];
	DDMA_SEND_DEST_IN  = &host_ddma_regs[1];
	DDMA_SEND_ADDR_IN  = &host_ddma_regs[2];
	DDMA_SEND_SIZE_IN  = &host_ddma_regs[3];
	DDMA_SEND_CMD_IN   = &host_ddma_regs[4];
	DDMA_STATUS        = &host_ddma_regs[5];
	DDMA_RECV_ADDR_IN  = &host_ddma_regs[6];
	DDMA_RECV_ADDR_OUT = &host_ddma_regs[7];
	DDMA_RECV_SIZE_OUT = &host_ddma_regs[8];
	DDMA_RECV_CMD_IN   = &host_ddma_regs[9];
}
