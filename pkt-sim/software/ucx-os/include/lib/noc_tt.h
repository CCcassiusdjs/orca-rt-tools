/* file:          noc_tt.h
 * description:   time-triggered injection of the packets between PEs
 *                (lib/noc_tt.c)
 *
 * Build with -DUCX_NOC_TT (kernel and application; Makefile, TR_DEFS and
 * TT_DEFS). Without UCX_NOC_TT the library defines nothing.
 */
#ifndef UCX_NOC_TT_H
#define UCX_NOC_TT_H

/* noc_packet_t of lib/noc.h, uint16_t and uint32_t of hal.h (include/ucx.h) */

/* injection instant of a packet, from the tick that starts the phase of
 * the job that sends it: `ticks` ticks later, at step `count` of TIMER1
 * (16 cycles per step, hal.c), so `ticks` T + 16 `count` cycles after that
 * tick (T: tick period in cycles) */
struct ucx_tt_at {
	uint16_t ticks;
	uint16_t count;
};

/* index of the current tick (number of ticks since the timer started) */
uint32_t ucx_noc_tt_ticks(void);

/* tick routine (kernel/sched.c, dispatch, before the tick hook of the
 * application): counts the tick and injects or arms the next packet */
void ucx_noc_tt_tick(void);

/* hands packet `pkt` to the kernel: a target on this PE receives it now
 * (ucx_noc_send); a target on another PE receives it at the instant `at`
 * counted from tick `tick` (the tick of the phase of the sending job). The
 * kernel writes the target and the tag into the packet at the injection,
 * so the job can reuse `pkt` for its next packet of the same flow. Returns
 * the value of ucx_noc_send for a target on this PE; for another PE, 0
 * (the kernel keeps the packet) or UCX_NOC_OUT_OF_MEMORY (queue full,
 * packet not sent) */
uint32_t ucx_noc_send_at(uint16_t target_cpu, uint16_t target_port, noc_packet_t *pkt, uint16_t tag,
	uint32_t tick, const struct ucx_tt_at *at);

/* packets that wait for their instant on this PE */
uint32_t ucx_noc_tt_pending(void);

#endif
