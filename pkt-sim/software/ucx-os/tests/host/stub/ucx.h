/* test ucx.h for the host: includes only what is needed to compile
 * lib/noc.c, lib/queue.c e device/ddma.c. */
#ifndef HOST_UCX_H
#define HOST_UCX_H
#include <hal.h>
#include <lib/queue.h>

#define TASK_READY   1
#define TASK_BLOCKED 2

struct tcb_s {
	struct tcb_s *tcb_next;
	uint16_t id;
	uint8_t state;
};

struct kcb_s {
	struct tcb_s *tcb_p;
};

extern struct kcb_s *kcb_p;
uint16_t ucx_task_id(void);

#include <device/ddma.h>
#include <lib/noc.h>
#endif
