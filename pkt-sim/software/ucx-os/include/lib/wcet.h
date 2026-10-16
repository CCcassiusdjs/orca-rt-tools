/* Loop bounds for the static WCET analysis (orca-rt-tools, rttools.wcet).
 *
 * WCET_LOOP_BOUND(n): placed at the start of the body of a loop, records
 * that the header of the innermost loop around this point runs at most n
 * times per entry into the loop. WCET_LOOP_TOTAL(n): the header runs at
 * most n times per call of the enclosing function (for a loop whose count
 * per entry varies, as the inner loop of an insertion sort).
 *
 * Each use writes two words in the section .wcet_bounds of the object file:
 * the address of the point in the code (the label 1 of the asm statement)
 * and n, with bit 31 set for WCET_LOOP_TOTAL. The section has the flag R
 * (SHF_GNU_RETAIN, GNU as 2.36 or later), so ld --gc-sections keeps it,
 * and no SHF_ALLOC flag: it stays in image.elf, outside the memory image
 * (objcopy -O binary leaves it out), and the linker resolves the address.
 * The asm statement emits no instruction; `n` must be a constant
 * expression below 2^31.
 */
#ifndef UCX_LIB_WCET_H
#define UCX_LIB_WCET_H

#define WCET_BOUND_WORDS_(n) \
	__asm__ volatile ("1:\n\t.pushsection .wcet_bounds,\"R\",@progbits\n\t.balign 4\n\t" \
			  ".word 1b\n\t.word %0\n\t.popsection" :: "i"(n))

#define WCET_LOOP_BOUND(n) WCET_BOUND_WORDS_((unsigned)(n))
#define WCET_LOOP_TOTAL(n) WCET_BOUND_WORDS_((unsigned)(n) | 0x80000000u)

#endif
