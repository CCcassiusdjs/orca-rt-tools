# Program of tb_cpu_cycles.vhd: blocks of 16 equal instructions (or
# sequences) between stores to 0x2000002C (marker). Image:
#   riscv64-elf-as -march=rv32e -mabi=ilp32e -o p.o cpu_cycles.s
#   riscv64-elf-ld -melf32lriscv -Ttext=0 -o p.elf p.o
#   riscv64-elf-objcopy -O binary p.elf p.bin
#   hexdump -v -e '4/1 "%02x" "\n"' p.bin > cpu_cycles.hex
# (the word format of code.txt in the ucx-os build).
	.text
	.globl _start
_start:
	lui a4,0x20000
	lui a3,0x1
	lui t1,0x1
# block 0 empty: marker store only
	sw zero,44(a4)
# block 1 alu: ALU, register and immediate
	sw zero,44(a4)
	addi a2,a2,1
	addi a2,a2,1
	addi a2,a2,1
	addi a2,a2,1
	addi a2,a2,1
	addi a2,a2,1
	addi a2,a2,1
	addi a2,a2,1
	addi a2,a2,1
	addi a2,a2,1
	addi a2,a2,1
	addi a2,a2,1
	addi a2,a2,1
	addi a2,a2,1
	addi a2,a2,1
	addi a2,a2,1
# block 2 lui: upper immediate
	sw zero,44(a4)
	lui a2,0x40003
	lui a2,0x40003
	lui a2,0x40003
	lui a2,0x40003
	lui a2,0x40003
	lui a2,0x40003
	lui a2,0x40003
	lui a2,0x40003
	lui a2,0x40003
	lui a2,0x40003
	lui a2,0x40003
	lui a2,0x40003
	lui a2,0x40003
	lui a2,0x40003
	lui a2,0x40003
	lui a2,0x40003
# block 3 lw: load word from RAM
	sw zero,44(a4)
	lw a2,0(a3)
	lw a2,0(a3)
	lw a2,0(a3)
	lw a2,0(a3)
	lw a2,0(a3)
	lw a2,0(a3)
	lw a2,0(a3)
	lw a2,0(a3)
	lw a2,0(a3)
	lw a2,0(a3)
	lw a2,0(a3)
	lw a2,0(a3)
	lw a2,0(a3)
	lw a2,0(a3)
	lw a2,0(a3)
	lw a2,0(a3)
# block 4 lhu: load half word
	sw zero,44(a4)
	lhu a2,0(a3)
	lhu a2,0(a3)
	lhu a2,0(a3)
	lhu a2,0(a3)
	lhu a2,0(a3)
	lhu a2,0(a3)
	lhu a2,0(a3)
	lhu a2,0(a3)
	lhu a2,0(a3)
	lhu a2,0(a3)
	lhu a2,0(a3)
	lhu a2,0(a3)
	lhu a2,0(a3)
	lhu a2,0(a3)
	lhu a2,0(a3)
	lhu a2,0(a3)
# block 5 lbu: load byte
	sw zero,44(a4)
	lbu a2,0(a3)
	lbu a2,0(a3)
	lbu a2,0(a3)
	lbu a2,0(a3)
	lbu a2,0(a3)
	lbu a2,0(a3)
	lbu a2,0(a3)
	lbu a2,0(a3)
	lbu a2,0(a3)
	lbu a2,0(a3)
	lbu a2,0(a3)
	lbu a2,0(a3)
	lbu a2,0(a3)
	lbu a2,0(a3)
	lbu a2,0(a3)
	lbu a2,0(a3)
# block 6 sw: store word to RAM
	sw zero,44(a4)
	sw a2,0(a3)
	sw a2,0(a3)
	sw a2,0(a3)
	sw a2,0(a3)
	sw a2,0(a3)
	sw a2,0(a3)
	sw a2,0(a3)
	sw a2,0(a3)
	sw a2,0(a3)
	sw a2,0(a3)
	sw a2,0(a3)
	sw a2,0(a3)
	sw a2,0(a3)
	sw a2,0(a3)
	sw a2,0(a3)
	sw a2,0(a3)
# block 7 sh: store half word
	sw zero,44(a4)
	sh a2,0(a3)
	sh a2,0(a3)
	sh a2,0(a3)
	sh a2,0(a3)
	sh a2,0(a3)
	sh a2,0(a3)
	sh a2,0(a3)
	sh a2,0(a3)
	sh a2,0(a3)
	sh a2,0(a3)
	sh a2,0(a3)
	sh a2,0(a3)
	sh a2,0(a3)
	sh a2,0(a3)
	sh a2,0(a3)
	sh a2,0(a3)
# block 8 sb: store byte
	sw zero,44(a4)
	sb a2,0(a3)
	sb a2,0(a3)
	sb a2,0(a3)
	sb a2,0(a3)
	sb a2,0(a3)
	sb a2,0(a3)
	sb a2,0(a3)
	sb a2,0(a3)
	sb a2,0(a3)
	sb a2,0(a3)
	sb a2,0(a3)
	sb a2,0(a3)
	sb a2,0(a3)
	sb a2,0(a3)
	sb a2,0(a3)
	sb a2,0(a3)
# block 9 sw_mmio: store to 0x20000028 (CACC_REGISTER)
	sw zero,44(a4)
	sw a0,40(a4)
	sw a0,40(a4)
	sw a0,40(a4)
	sw a0,40(a4)
	sw a0,40(a4)
	sw a0,40(a4)
	sw a0,40(a4)
	sw a0,40(a4)
	sw a0,40(a4)
	sw a0,40(a4)
	sw a0,40(a4)
	sw a0,40(a4)
	sw a0,40(a4)
	sw a0,40(a4)
	sw a0,40(a4)
	sw a0,40(a4)
# block 10 lw_mmio: load from 0x20000028
	sw zero,44(a4)
	lw a2,40(a4)
	lw a2,40(a4)
	lw a2,40(a4)
	lw a2,40(a4)
	lw a2,40(a4)
	lw a2,40(a4)
	lw a2,40(a4)
	lw a2,40(a4)
	lw a2,40(a4)
	lw a2,40(a4)
	lw a2,40(a4)
	lw a2,40(a4)
	lw a2,40(a4)
	lw a2,40(a4)
	lw a2,40(a4)
	lw a2,40(a4)
# block 11 branch_taken: taken branch
	sw zero,44(a4)
	beq zero,zero,1f
1:
	beq zero,zero,1f
1:
	beq zero,zero,1f
1:
	beq zero,zero,1f
1:
	beq zero,zero,1f
1:
	beq zero,zero,1f
1:
	beq zero,zero,1f
1:
	beq zero,zero,1f
1:
	beq zero,zero,1f
1:
	beq zero,zero,1f
1:
	beq zero,zero,1f
1:
	beq zero,zero,1f
1:
	beq zero,zero,1f
1:
	beq zero,zero,1f
1:
	beq zero,zero,1f
1:
	beq zero,zero,1f
1:
# block 12 branch_not_taken: branch not taken
	sw zero,44(a4)
	bne zero,zero,1f
1:
	bne zero,zero,1f
1:
	bne zero,zero,1f
1:
	bne zero,zero,1f
1:
	bne zero,zero,1f
1:
	bne zero,zero,1f
1:
	bne zero,zero,1f
1:
	bne zero,zero,1f
1:
	bne zero,zero,1f
1:
	bne zero,zero,1f
1:
	bne zero,zero,1f
1:
	bne zero,zero,1f
1:
	bne zero,zero,1f
1:
	bne zero,zero,1f
1:
	bne zero,zero,1f
1:
	bne zero,zero,1f
1:
# block 13 jal: jump
	sw zero,44(a4)
	jal zero,1f
1:
	jal zero,1f
1:
	jal zero,1f
1:
	jal zero,1f
1:
	jal zero,1f
1:
	jal zero,1f
1:
	jal zero,1f
1:
	jal zero,1f
1:
	jal zero,1f
1:
	jal zero,1f
1:
	jal zero,1f
1:
	jal zero,1f
1:
	jal zero,1f
1:
	jal zero,1f
1:
	jal zero,1f
1:
	jal zero,1f
1:
# block 14 call_ret: call of a function that only returns: jal + jalr
	sw zero,44(a4)
	jal ra,callee
	jal ra,callee
	jal ra,callee
	jal ra,callee
	jal ra,callee
	jal ra,callee
	jal ra,callee
	jal ra,callee
	jal ra,callee
	jal ra,callee
	jal ra,callee
	jal ra,callee
	jal ra,callee
	jal ra,callee
	jal ra,callee
	jal ra,callee
# block 15 call_body: call of the code of set_cacc (device/cacc.c): jal + lui + lw + sw + jalr
	sw zero,44(a4)
	jal ra,setc
	jal ra,setc
	jal ra,setc
	jal ra,setc
	jal ra,setc
	jal ra,setc
	jal ra,setc
	jal ra,setc
	jal ra,setc
	jal ra,setc
	jal ra,setc
	jal ra,setc
	jal ra,setc
	jal ra,setc
	jal ra,setc
	jal ra,setc
# block 16 inc64: 64-bit increment of disp_timer (kernel/sched.c): lui + 2 lw + addi + sltu + add + 2 sw
	sw zero,44(a4)
	lui a3,0x1
	lw a1,0(a3)
	lw a2,4(a3)
	addi a0,a1,1
	sltu a1,a0,a1
	add a1,a1,a2
	sw a0,0(a3)
	sw a1,4(a3)
	lui a3,0x1
	lw a1,0(a3)
	lw a2,4(a3)
	addi a0,a1,1
	sltu a1,a0,a1
	add a1,a1,a2
	sw a0,0(a3)
	sw a1,4(a3)
	lui a3,0x1
	lw a1,0(a3)
	lw a2,4(a3)
	addi a0,a1,1
	sltu a1,a0,a1
	add a1,a1,a2
	sw a0,0(a3)
	sw a1,4(a3)
	lui a3,0x1
	lw a1,0(a3)
	lw a2,4(a3)
	addi a0,a1,1
	sltu a1,a0,a1
	add a1,a1,a2
	sw a0,0(a3)
	sw a1,4(a3)
	lui a3,0x1
	lw a1,0(a3)
	lw a2,4(a3)
	addi a0,a1,1
	sltu a1,a0,a1
	add a1,a1,a2
	sw a0,0(a3)
	sw a1,4(a3)
	lui a3,0x1
	lw a1,0(a3)
	lw a2,4(a3)
	addi a0,a1,1
	sltu a1,a0,a1
	add a1,a1,a2
	sw a0,0(a3)
	sw a1,4(a3)
	lui a3,0x1
	lw a1,0(a3)
	lw a2,4(a3)
	addi a0,a1,1
	sltu a1,a0,a1
	add a1,a1,a2
	sw a0,0(a3)
	sw a1,4(a3)
	lui a3,0x1
	lw a1,0(a3)
	lw a2,4(a3)
	addi a0,a1,1
	sltu a1,a0,a1
	add a1,a1,a2
	sw a0,0(a3)
	sw a1,4(a3)
	lui a3,0x1
	lw a1,0(a3)
	lw a2,4(a3)
	addi a0,a1,1
	sltu a1,a0,a1
	add a1,a1,a2
	sw a0,0(a3)
	sw a1,4(a3)
	lui a3,0x1
	lw a1,0(a3)
	lw a2,4(a3)
	addi a0,a1,1
	sltu a1,a0,a1
	add a1,a1,a2
	sw a0,0(a3)
	sw a1,4(a3)
	lui a3,0x1
	lw a1,0(a3)
	lw a2,4(a3)
	addi a0,a1,1
	sltu a1,a0,a1
	add a1,a1,a2
	sw a0,0(a3)
	sw a1,4(a3)
	lui a3,0x1
	lw a1,0(a3)
	lw a2,4(a3)
	addi a0,a1,1
	sltu a1,a0,a1
	add a1,a1,a2
	sw a0,0(a3)
	sw a1,4(a3)
	lui a3,0x1
	lw a1,0(a3)
	lw a2,4(a3)
	addi a0,a1,1
	sltu a1,a0,a1
	add a1,a1,a2
	sw a0,0(a3)
	sw a1,4(a3)
	lui a3,0x1
	lw a1,0(a3)
	lw a2,4(a3)
	addi a0,a1,1
	sltu a1,a0,a1
	add a1,a1,a2
	sw a0,0(a3)
	sw a1,4(a3)
	lui a3,0x1
	lw a1,0(a3)
	lw a2,4(a3)
	addi a0,a1,1
	sltu a1,a0,a1
	add a1,a1,a2
	sw a0,0(a3)
	sw a1,4(a3)
	lui a3,0x1
	lw a1,0(a3)
	lw a2,4(a3)
	addi a0,a1,1
	sltu a1,a0,a1
	add a1,a1,a2
	sw a0,0(a3)
	sw a1,4(a3)
	sw zero,44(a4)
2:	jal zero,2b
callee:	jalr zero,0(ra)
# set_cacc of device/cacc.c (-ffixed-a5 keeps a5 free in the kernel; any
# register gives the same cycles)
setc:	lui a5,0x1
	lw a5,8(a5)
	sw a0,0(a5)
	jalr zero,0(ra)
