/* file:          tick_release.h
 * description:   release by tick of the phase model (lib/tick_release.c)
 *
 * Build with -DUCX_APP_IRQ4 -DUCX_APP_TICK -DUCX_TICK_RELEASE (kernel and
 * application; Makefile, TR_DEFS). Without UCX_TICK_RELEASE the library
 * defines nothing.
 */
#ifndef UCX_TICK_RELEASE_H
#define UCX_TICK_RELEASE_H

/* uint32_t and uint16_t of hal.h (include/ucx.h) */

/* index of the current phase of this PE: the number of release
 * interrupts that a tick has applied (0 before the first release) */
uint32_t ucx_phase(void);

/* blocks the calling task until the tick of phase `phase` and of a phase
 * after the phase of its previous start; returns the phase of the start */
uint32_t ucx_phase_wait(uint32_t phase);

/* nonzero while task `task_id` waits in ucx_phase_wait (lib/noc.c does
 * not wake such a task on a packet arrival) */
int ucx_phase_waiting(uint16_t task_id);

#endif
