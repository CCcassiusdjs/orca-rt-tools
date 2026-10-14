# Program of tb_cpu_irq.vhd (images cpu_irq.hex and cpu_irq_guard.hex, built as
# cpu_cycles.hex of cpu_cycles.s with -march=rv32e; cpu_irq_guard.hex with
# --defsym UCX_ISR_RETURN_GUARD=1, the _isr of crt0.s of the time-triggered
# applications). Interrupt return of crt0.s (_isr,
# ucx-os/arch/riscv/hf-riscv-e) under interrupts that arrive at every cycle
# offset of the return. The handler acknowledges the source (store to
# 0x20000040). Mode (tp, from the testbench):
#   0: the handler leaves interrupts disabled (default of the UCX-OS kernel);
#   1: the handler enables interrupts before it returns, as the irq handlers
#      and dispatch() of UCX-OS do when built with -DUCX_ISR_NESTING (_ei,
#      _interrupt_tick);
#   2: as 0, and the main loop also resumes a context saved by an interrupt
#      through the return of _isr with interrupts disabled, as yield() of
#      UCX-OS does when the next task was preempted by the tick (dispatch()
#      saved its context inside _isr): the interrupts that arrive while
#      interrupts are disabled are taken at the `sb` of that return.
# The main loop stores its counter to 0x2000002C and stops at 0x20000030
# when sp differs from its value.
	.text
	.globl _start
_start:
	li	sp, 0x1f00
	la	t0, _isr
	li	t1, 0xf0000000
	sw	t0, 0(t1)
	li	t1, 0xf0000020
	li	t0, 1
	sw	t0, 0(t1)
	lui	a4, 0x20000
	lw	tp, 56(a4)		# mode from the testbench
	li	a0, 1
	jal	ra, _interrupt_set
	mv	s1, sp
	li	s0, 0
loop:
	addi	s0, s0, 1
	lui	a4, 0x20000
	sw	s0, 44(a4)
	bne	sp, s1, fail
	li	t0, 2
	bne	tp, t0, loop
	# mode 2: interrupts disabled, a wait of (s0 mod 64) iterations, a
	# frame of _isr whose return address is `loop`, and the return of _isr.
	# An interrupt raised before the store that disables interrupts is
	# taken after it, and its return enables interrupts again: the store
	# repeats until IRQ_STATUS reads 0 four cycles after it
	li	a1, 0xf0000030
3:	sw	zero, 0(a1)
	nop
	nop
	nop
	nop
	lw	t0, 0(a1)
	bne	t0, zero, 3b
	andi	t0, s0, 63
1:	beq	t0, zero, 2f
	addi	t0, t0, -1
	j	1b
2:	addi	sp, sp, -40
	la	t0, loop
	sw	t0, 36(sp)
	sw	ra, 0(sp)
	sw	zero, 4(sp)
	sw	zero, 8(sp)
	sw	zero, 12(sp)
	sw	zero, 16(sp)
	sw	zero, 20(sp)
	sw	zero, 24(sp)
	sw	zero, 28(sp)
	sw	zero, 32(sp)
	j	_isr_return
fail:
	lui	a4, 0x20000
	sw	sp, 48(a4)
	j	fail

	.org 0x100
_isr:
	nop
	addi	sp, sp, -40
	sw	ra, 0(sp)
	sw	t0, 4(sp)
	sw	t1, 8(sp)
	sw	t2, 12(sp)
	sw	a0, 16(sp)
	sw	a1, 20(sp)
	sw	a2, 24(sp)
	sw	a3, 28(sp)
	sw	a4, 32(sp)
	li	a5, 0xf0000040
	lw	a5, 0(a5)
	addi	a5, a5, -4
.ifdef UCX_ISR_RETURN_GUARD
	la	a0, _isr_resume
	sub	a0, a5, a0
	sltiu	a0, a0, 8
	beq	a0, zero, 1f
	lw	a5, 36(sp)
1:
.endif
	sw	a5, 36(sp)
	lui	a1, 0xf0000
	lw	a0, 0x10(a1)
	lw	a2, 0x20(a1)
	and	a0, a0, a2
	addi	a1, sp, 0
	jal	ra, irq_handler
_isr_return:
	lw	ra, 0(sp)
	lw	t0, 4(sp)
	lw	t1, 8(sp)
	lw	t2, 12(sp)
	lw	a0, 16(sp)
	lw	a1, 20(sp)
	lw	a2, 24(sp)
	lw	a3, 28(sp)
	lw	a4, 32(sp)
	li	a5, 0xf0000030
	ori	a5, a5, 0x1
	addi	sp, sp, 40
	sb	a5, 0(a5)
_isr_resume:
	lw	a5, -4(sp)
	jalr	zero, a5

_interrupt_set:
	li	a1, 0xf0000030
	lw	a2, 0(a1)
	sw	a0, 0(a1)
	addi	a0, a2, 0
	ret

irq_handler:
	addi	sp, sp, -16
	sw	ra, 12(sp)
	lui	a1, 0x20000
	sw	zero, 64(a1)		# acknowledge: the testbench lowers extio_in(0)
	li	a0, 1
	bne	tp, a0, 1f
	jal	ra, _interrupt_set	# _ei() before the return of the handler (mode 1)
1:	addi	a2, a2, 1
	addi	a2, a2, 1
	lw	ra, 12(sp)
	addi	sp, sp, 16
	ret
