extern volatile uint32_t * CACC_REGISTER;
extern volatile uint32_t * CACC_COUNTER1;
extern volatile uint32_t * CACC_COUNTER2;

extern volatile uint32_t * CACC_COUNTER3;
extern volatile uint32_t * CACC_COUNTER4;
extern volatile uint32_t * CACC_ITER;


void set_cacc(uint32_t v);
uint32_t get_cacc();

void set_counter_1(uint32_t v);
uint32_t get_counter_1();

void set_counter_2(uint32_t v);
uint32_t get_counter_2();

void set_counter_3(uint32_t v);
uint32_t get_counter_3();

void set_counter_4(uint32_t v);
uint32_t get_counter_3();

// Iteration marker (0x2000003C). The application writes one word at the
// begin and one at the end of the work of each iteration of a task; the
// PE prints `<t> <x-y> ITER begin|end <task> <k>` (manycore_pe.sv).
// Word: bit 31 = 1 at the end, 0 at the begin; bits 30:24 = task letter
// (ASCII); bits 23:0 = iteration k (1, 2, ...).
#define ITER_MARK_END 0x80000000u
#define ITER_MARK(task, k) (((uint32_t)(task) << 24) | ((uint32_t)(k) & 0x00FFFFFFu))
#define ITER_BEGIN(task, k) set_iter_mark(ITER_MARK(task, k))
#define ITER_END(task, k) set_iter_mark(ITER_MARK_END | ITER_MARK(task, k))

void set_iter_mark(uint32_t v);
