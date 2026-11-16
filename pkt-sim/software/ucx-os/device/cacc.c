#include <ucx.h>

volatile uint32_t* CACC_REGISTER = (volatile uint32_t *)(0x20000028);
volatile uint32_t* CACC_COUNTER1 = (volatile uint32_t *)(0x2000002C);
volatile uint32_t* CACC_COUNTER2 = (volatile uint32_t *)(0x20000030);

volatile uint32_t* CACC_COUNTER3 = (volatile uint32_t *)(0x20000034);
volatile uint32_t* CACC_COUNTER4 = (volatile uint32_t *)(0x20000038);

// iteration marker (see include/device/cacc.h)
volatile uint32_t* CACC_ITER = (volatile uint32_t *)(0x2000003C);

void set_cacc(uint32_t v){
  *CACC_REGISTER = v;
}

uint32_t get_cacc(){
  return *CACC_REGISTER;
}

void set_counter_1(uint32_t v){
  *CACC_COUNTER1 = v;
}

uint32_t get_counter_1(){
  return *CACC_COUNTER1;
}

void set_counter_2(uint32_t v){
  *CACC_COUNTER2 = v;
}

uint32_t get_counter_2(){
  return *CACC_COUNTER2;
}

void set_counter_3(uint32_t v){
  *CACC_COUNTER3 = v;
}

uint32_t get_counter_3(){
  return *CACC_COUNTER3;
}

void set_counter_4(uint32_t v){
  *CACC_COUNTER4 = v;
}

uint32_t get_counter_4(){
  return *CACC_COUNTER4;
}

void set_iter_mark(uint32_t v){
  *CACC_ITER = v;
}
