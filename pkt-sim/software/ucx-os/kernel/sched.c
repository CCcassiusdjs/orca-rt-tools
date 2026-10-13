/* file:          sched.c
 * description:   UCX/OS kernel scheduler
 * date:          05/2023
 * author:        Sergio Johann Filho <sergio.johann@acad.pucrs.br>
 */

#include <ucx.h>


/* actual dispatch/yield implementation may be platform dependent */

void _dispatch(void) __attribute__ ((weak, alias ("dispatch")));
void _yield(void) __attribute__ ((weak, alias ("yield")));

void wake_up_init(){
  IRQ_MASK |= MASK_IRQ4;
}




/* kernel auxiliary functions */

static void krnl_stack_check(void)
{
	uint32_t check = 0x33333333;
	uint32_t *stack_p = (uint32_t *)kcb_p->tcb_p->stack;
	
	if (*stack_p != check) {
		ucx_hexdump((void *)kcb_p->tcb_p->stack, kcb_p->tcb_p->stack_sz);
		printf("\n*** HALT - task %d, stack %08x (%d) check failed\n", kcb_p->tcb_p->id,
			(uint32_t)kcb_p->tcb_p->stack, (uint32_t)kcb_p->tcb_p->stack_sz);
		for (;;);
	}
}

static void krnl_delay_update(void)
{
	struct tcb_s *tcb_ptr = kcb_p->tcb_first;
	
	for (;;	tcb_ptr = tcb_ptr->tcb_next) {
		if (tcb_ptr->state == TASK_BLOCKED && tcb_ptr->delay > 0) {
			tcb_ptr->delay--;
			if (tcb_ptr->delay == 0)
				tcb_ptr->state = TASK_READY;
		}
		if (tcb_ptr->tcb_next == kcb_p->tcb_first) break;
	}
}

// uint16_t krnl_rt_timer = 0;
// uint16_t krnl_rt_hyperp = 0;

/* real time scheduler*/
int32_t krnl_rt_schedule(void){
  // update hyperperiod timer
  //krnl_rt_timer = ((krnl_rt_timer + 1) % krnl_rt_hyperp);

  // update current executing task capacity
  // RT => kcb_p->tcb_p->rt->period != 0
  // find next task to execute based on scheduling policy

  // update selected task info

  return -1;
}

#ifndef SET_HP
#define SET_HP(A) (krnl_rt_hyperp = A;)
#endif 

long unsigned int sched_counter = 0;
long long unsigned int disp_timer = 0;

// #define volatile unsigned int* cacc_timer = 0x20000028;
/* task scheduler and dispatcher */

uint16_t krnl_schedule(int block)
{  
  // *((volatile int*)(0x20000050)) = 0x1;
#ifndef UCX_NO_INSTRUMENTATION
  disp_timer++;
  set_cacc(disp_timer);
  set_counter_1(0);
#endif

  // put current task into ready state if still running
  if(block) {
    kcb_p->tcb_p->state = TASK_BLOCKED;
  } else if (kcb_p->tcb_p->state == TASK_RUNNING){
    kcb_p->tcb_p->state = TASK_READY;
  }

  struct tcb_s* current_task = kcb_p->tcb_p;

  do {
    // advance to next task in the circular queue
    kcb_p->tcb_p = kcb_p->tcb_p->tcb_next;

    // no more tasks to search, skip
    if (kcb_p->tcb_p->id == current_task->id) {
        break;
    }

  // keep seaching for tasks in ready state
  } while (kcb_p->tcb_p->state != TASK_READY || kcb_p->tcb_p->id == 0);

  // if no task is available, go idling
  if (kcb_p->tcb_p->state != TASK_READY){
    kcb_p->tcb_p = kcb_p->tcb_first;
  }

  // put next task into running state
	kcb_p->tcb_p->state = TASK_RUNNING;
  
#ifndef UCX_NO_INSTRUMENTATION
  set_counter_2(kcb_p->tcb_p->id);
#endif
  // *((volatile int*)(0x20000050)) = 0x2;
	return kcb_p->tcb_p->id;
}

void krnl_dispatcher(void)
{
	_dispatch();
}

void ucx_task_yield()
{
	_yield();
}

void dispatch(void)
{
	if (!setjmp(kcb_p->tcb_p->context)) {
		krnl_delay_update();
		krnl_stack_check();

    krnl_schedule(0);

		// printf("SCHED %d %d %s ##\n", sched_counter++, kcb_p->tcb_p->id, kcb_p->tcb_p->name);
		// printf("tcb_next:     0x%x   task:         0x%x\n", kcb_p->tcb_p->tcb_next, kcb_p->tcb_p->task);
		// printf("context:      0x%x   stack:        0x%x\n", kcb_p->tcb_p->context, kcb_p->tcb_p->stack);
		// printf("stack_sz:     0x%x   delay:        0x%x\n", kcb_p->tcb_p->stack_sz, kcb_p->tcb_p->delay);
		// printf("priority:     0x%x   rt->period:   0x%x\n", kcb_p->tcb_p->priority, kcb_p->tcb_p->rt->period);
		// printf("rt->capacity: 0x%x   rt->deadline: 0x%x\n", kcb_p->tcb_p->rt->capacity, kcb_p->tcb_p->rt->deadline);
		
		_interrupt_tick();
		longjmp(kcb_p->tcb_p->context, 1);
	}
}

void yield(void)
{
	if (!setjmp(kcb_p->tcb_p->context)) {
		/* TODO: check if we need to run a delay update on yields. maybe only on a non-preemtive execution? */ 
		krnl_delay_update();
		krnl_stack_check();
		krnl_schedule(1);
		longjmp(kcb_p->tcb_p->context, 1);
	}
}



// Release interrupt (manycore_pe.sv, wake-up generator). This handler is
// the one of application E (weird_a.c). An application that releases other
// tasks (rttools.ucxgen, app/car_v.c) defines its own irq4_handler and
// builds the kernel with -DUCX_APP_IRQ4 (Makefile, generated applications);
// without the macro, the preprocessed source is the one of run F.
#ifndef UCX_APP_IRQ4
void irq4_handler(void){
  _di();
  // task A must reside in node 0
  if(ucx_noc_cpu_id() == 0){

    struct tcb_s* current_task = kcb_p->tcb_p;

    do {
      if(strcmp(current_task->name, "A") == 0){
        current_task->state = TASK_READY;
        break;
      } else {
        current_task = current_task->tcb_next;
      }
    } while (1);
  }

  // flag interruption down
  volatile int* irq_flag_down = (volatile int*)(0x2000004C);
  *irq_flag_down = !(*irq_flag_down);

  _ei();
}
#endif