# Program of tb_cpu_irq.vhd (image cpu_irq.hex, built as cpu_cycles.hex of
# cpu_cycles.s with -march=rv32e). Interrupt return of crt0.s (_isr, ucx-os/arch/riscv/hf-riscv-e) under
# interrupts that arrive at every cycle offset of the return. The handler
# acknowledges the source (store to 0x20000040) and, when tp != 0, enables
# interrupts before it returns, as the irq handlers and dispatch() of
# UCX-OS do when built with -DUCX_ISR_NESTING (_ei, _interrupt_tick). The main loop stores its counter to
# 0x2000002C and stops at 0x20000030 when sp differs from its value.
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
	lw	tp, 56(a4)		# mode from the testbench: 1 = enable in the handler
	li	a0, 1
	jal	ra, _interrupt_set
	mv	s1, sp
	li	s0, 0
loop:
	addi	s0, s0, 1
	lui	a4, 0x20000
	sw	s0, 44(a4)
	bne	sp, s1, fail
	j	loop
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
	sw	a5, 36(sp)
	lui	a1, 0xf0000
	lw	a0, 0x10(a1)
	lw	a2, 0x20(a1)
	and	a0, a0, a2
	addi	a1, sp, 0
	jal	ra, irq_handler
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
	beq	tp, zero, 1f
	li	a0, 1
	jal	ra, _interrupt_set	# _ei() before the return of the handler
1:	addi	a2, a2, 1
	addi	a2, a2, 1
	lw	ra, 12(sp)
	addi	sp, sp, 16
	ret
