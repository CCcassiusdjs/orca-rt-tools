/* The kernel writes these registers in each dispatch (sched.c) and packet
 * event (noc.c); the RTL logs the writes. -DUCX_NO_INSTRUMENTATION removes
 * the writes (experiments/exp23/build_sw.sh builds both variants to bound
 * the cost of the writes). */
extern volatile uint32_t * CACC_REGISTER;
extern volatile uint32_t * CACC_COUNTER1;
extern volatile uint32_t * CACC_COUNTER2;

extern volatile uint32_t * CACC_COUNTER3;
extern volatile uint32_t * CACC_COUNTER4;


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