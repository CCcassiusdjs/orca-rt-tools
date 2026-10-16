/* test hal.h for the host (x86_64). Replaces arch/<cpu>/hal.h only for
 * the tests in tests/host; it is not part of the target build. */
#ifndef HOST_HAL_H
#define HOST_HAL_H
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <setjmp.h>
#include <stdlib.h>   /* before the malloc/free macros */
#include <string.h>

void *ucx_malloc(uint32_t size);
void ucx_free(void *ptr);
#define malloc(n) ucx_malloc(n)
#define free(p)   ucx_free(p)

void _di(void);
void _ei(void);

extern volatile uint32_t host_irq_mask;
#define IRQ_MASK  host_irq_mask
#define MASK_IRQ1 0x02
#define MASK_IRQ2 0x04
#define MASK_IRQ3 0x08

/* TIMER1 and the timer causes of segment 0 (lib/noc_tt.c) and the cause
 * register of the interrupt controller */
extern volatile uint32_t host_timer1, host_timer1ocr, host_timercauseinv, host_timermask, host_irq_cause;
#define TIMER1         host_timer1
#define TIMER1OCR      host_timer1ocr
#define TIMERCAUSEINV  host_timercauseinv
#define TIMERMASK      host_timermask
#define MASK_TIMER1OCR (1 << 3)
#define IRQ_CAUSE      host_irq_cause
#define MASK_IRQ4      0x10

void set_counter_3(uint32_t v);
void set_counter_4(uint32_t v);
#endif
