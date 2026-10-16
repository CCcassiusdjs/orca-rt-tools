/* task priorities */
#define TASK_CRIT_PRIO		((0x03 << 8) | 0x03)		/* priority 0 .. 3 */
#define TASK_HIGH_PRIO 		((0x0f << 8) | 0x0f)		/* priority 4 .. 15 */
#define TASK_NORMAL_PRIO	((0x1f << 8) | 0x1f)		/* priority 16 .. 31 */
#define TASK_LOW_PRIO		((0x3f << 8) | 0x3f)		/* priority 32 .. 63 */
#define TASK_IDLE_PRIO		((0x7f << 8) | 0x7f)		/* priority 64 .. 127 */

void wake_up_init();

/* task states */
enum {TASK_STOPPED, TASK_READY, TASK_RUNNING, TASK_BLOCKED, TASK_SUSPENDED};

struct rt_s {
  uint16_t period;
  uint16_t capacity;
  uint16_t deadline;
  int (*rt_sched)(void);
};

/* task control block node */
struct tcb_s {
	struct tcb_s *tcb_next;
	void (*task)(void);
	jmp_buf context;		/* jmp_buf is architecture specific */
	size_t *stack;
	size_t stack_sz;
	uint16_t id;
	uint16_t delay;
	uint16_t priority;
	uint8_t state;
	char name[5];
	struct rt_s *rt;
};

/* kernel control block */
struct kcb_s {
	jmp_buf context;
	struct tcb_s *tcb_p;
	struct tcb_s *tcb_first;
	struct queue_s *events;
	volatile uint32_t ctx_switches;
	char preemptive;
	uint16_t id;
};


void ucx_sleep(int32_t cycles);

int32_t tprintf(const char *fmt, ...);

extern struct kcb_s *kcb_p;

/* kernel API */

#define CRITICAL_ENTER()({kcb_p->preemptive == 'y' ? _di() : 0; })
#define CRITICAL_LEAVE()({kcb_p->preemptive == 'y' ? _ei() : 0; })

uint16_t krnl_schedule(int block);
void krnl_dispatcher(void);

void ucx_task_hang(uint16_t cycles);
int32_t ucx_task_add(void *task, char* name, uint16_t stack_size,
 uint16_t period, uint16_t capacity, uint16_t deadline);
int32_t ucx_task_remove(uint16_t id);
void ucx_task_yield();
void ucx_task_delay(uint16_t ticks);
int32_t ucx_task_suspend(uint16_t id);
int32_t ucx_task_resume(uint16_t id);
int32_t ucx_task_priority(uint16_t id, uint16_t priority);
uint16_t ucx_task_id();
void ucx_task_wfi();
uint16_t ucx_task_count();
int32_t app_main();
