/* test ucx.h for the host: includes only what is needed to compile
 * lib/noc.c, lib/queue.c e device/ddma.c. */
#ifndef HOST_UCX_H
#define HOST_UCX_H
#include <hal.h>
#include <lib/queue.h>

#define TASK_READY   1
#define TASK_BLOCKED 2
#define TASK_RUNNING 3

struct tcb_s {
	struct tcb_s *tcb_next;
	uint16_t id;
	uint8_t state;
};

struct kcb_s {
	struct tcb_s *tcb_p;
	struct tcb_s *tcb_first;
};

extern struct kcb_s *kcb_p;
uint16_t ucx_task_id(void);

#include <device/ddma.h>
#include <device/cacc.h>   /* set_iter_mark and the ITER_* macros */
#include <lib/noc.h>
#include <lib/tick_release.h>
#include <lib/noc_tt.h>
#endif
