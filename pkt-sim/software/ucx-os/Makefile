TARGET_LIST = \
	'arm/versatilepb'  'arm/stm32f401_blackpill' \
	'avr/atmega32' 'avr/atmega328p' 'avr/atmega2560' \
	'mips/hf-risc' 'riscv/hf-riscv' 'riscv/hf-riscv-e' \
	'riscv/hf-riscv-llvm' 'riscv/riscv32-qemu' 'riscv/riscv32-qemu-llvm' \
	'riscv/riscv64-qemu' 'riscv/riscv64-qemu-llvm'

ARCH ?= none

SERIAL_BAUD=57600
SERIAL_DEVICE=/dev/ttyUSB0

SRC_DIR = .

BUILD_DIR = $(SRC_DIR)/build
BUILD_APP_DIR = $(BUILD_DIR)/app
BUILD_HAL_DIR = $(BUILD_DIR)/hal
BUILD_KERNEL_DIR = $(BUILD_DIR)/kernel
BUILD_TARGET_DIR = $(BUILD_DIR)/target

include $(BUILD_TARGET_DIR)/target.mak
include $(SRC_DIR)/arch/$(ARCH)/arch.mak

INC_DIRS += -I $(SRC_DIR)/include

incl:
ifeq ('$(ARCH)', 'none')
	@echo "You must specify a target architecture (ARCH=arch/target)."
	@echo "Supported targets are: $(TARGET_LIST)"
else
	@echo "ARCH = $(ARCH)" > $(BUILD_TARGET_DIR)/target.mak
endif

serial:
	stty ${SERIAL_BAUD} raw cs8 -parenb -crtscts clocal cread ignpar ignbrk -ixon -ixoff -ixany -brkint -icrnl -imaxbel -opost -onlcr -isig -icanon -iexten -echo -echoe -echok -echoctl -echoke -F ${SERIAL_DEVICE}

load: serial
	cat image.bin > $(SERIAL_DEVICE)

debug: serial
	cat ${SERIAL_DEVICE}

## RISC-V / Qemu
run_riscv32:
	echo "hit Ctrl+a x to quit"
#	qemu-system-riscv32 -machine virt -nographic -bios $(BUILD_TARGET_DIR)/image.bin -serial mon:stdio
	qemu-system-riscv32 -machine virt -bios none -kernel $(BUILD_TARGET_DIR)/image.elf -nographic

run_riscv64:
	echo "hit Ctrl+a x to quit"
	qemu-system-riscv64 -machine virt -bios none -kernel $(BUILD_TARGET_DIR)/image.elf -nographic
	
run_versatilepb:
	echo "hit Ctrl+a x to quit"
	qemu-system-arm -cpu arm1176 -m 128 -M versatilepb -serial stdio -kernel $(BUILD_TARGET_DIR)/image.elf

## kernel
ucx.pack: incl hal.pack libs.pack kernel.pack devices.pack 
	cp *.o $(SRC_DIR)/build/kernel
	$(AR) $(ARFLAGS) $(BUILD_TARGET_DIR)/libucxos.a $(BUILD_KERNEL_DIR)/*.o
	echo null > ucx.pack

kernel.pack: pipe.o semaphore.o sched.o event.o ucx.o main.o
	@echo null > kernel.pack

main.o: $(SRC_DIR)/init/main.c
	$(CC) $(CFLAGS) $(SRC_DIR)/init/main.c
ucx.o: $(SRC_DIR)/kernel/ucx.c
	$(CC) $(CFLAGS) $(SRC_DIR)/kernel/ucx.c
sched.o: $(SRC_DIR)/kernel/sched.c
	$(CC) $(CFLAGS) $(SRC_DIR)/kernel/sched.c
semaphore.o: $(SRC_DIR)/kernel/semaphore.c
	$(CC) $(CFLAGS) $(SRC_DIR)/kernel/semaphore.c
pipe.o: $(SRC_DIR)/kernel/pipe.c
	$(CC) $(CFLAGS) $(SRC_DIR)/kernel/pipe.c
event.o: $(SRC_DIR)/kernel/event.c
	$(CC) $(CFLAGS) $(SRC_DIR)/kernel/event.c

libs.pack: libc.o dump.o malloc.o list.o queue.o noc.o tick_release.o
	@echo null > libs.pack

queue.o: $(SRC_DIR)/lib/queue.c
	$(CC) $(CFLAGS) $(SRC_DIR)/lib/queue.c
list.o: $(SRC_DIR)/lib/list.c
	$(CC) $(CFLAGS) $(SRC_DIR)/lib/list.c
malloc.o: $(SRC_DIR)/lib/malloc.c
	$(CC) $(CFLAGS) $(SRC_DIR)/lib/malloc.c
dump.o: $(SRC_DIR)/lib/dump.c
	$(CC) $(CFLAGS) $(SRC_DIR)/lib/dump.c
libc.o: $(SRC_DIR)/lib/libc.c
	$(CC) $(CFLAGS) $(SRC_DIR)/lib/libc.c
noc.o: $(SRC_DIR)/lib/noc.c
	$(CC) $(CFLAGS) $(SRC_DIR)/lib/noc.c
tick_release.o: $(SRC_DIR)/lib/tick_release.c
	$(CC) $(CFLAGS) $(SRC_DIR)/lib/tick_release.c

devices.pack: ddma.o cacc.o
	@echo null > devices.pack
	
ddma.o: $(SRC_DIR)/device/ddma.c
	$(CC) $(CFLAGS) $(SRC_DIR)/device/ddma.c
cacc.o: $(SRC_DIR)/device/cacc.c
	$(CC) $(CFLAGS) $(SRC_DIR)/device/cacc.c

## kernel + application link
link:
ifeq ('$(ARCH)', 'avr/atmega32')
	$(LD) $(LDFLAGS) -o $(BUILD_TARGET_DIR)/image.elf $(BUILD_APP_DIR)/*.o -L$(BUILD_TARGET_DIR) -lucxos
else ifeq ('$(ARCH)', 'avr/atmega328p')
	$(LD) $(LDFLAGS) -o $(BUILD_TARGET_DIR)/image.elf $(BUILD_APP_DIR)/*.o -L$(BUILD_TARGET_DIR) -lucxos
else ifeq ('$(ARCH)', 'avr/atmega2560')
	$(LD) $(LDFLAGS) -o $(BUILD_TARGET_DIR)/image.elf $(BUILD_APP_DIR)/*.o -L$(BUILD_TARGET_DIR) -lucxos
else 
	$(LD) $(LDFLAGS) -T$(LDSCRIPT) -Map $(BUILD_TARGET_DIR)/image.map -o $(BUILD_TARGET_DIR)/image.elf $(BUILD_APP_DIR)/*.o -L$(BUILD_TARGET_DIR) -lucxos
endif
	$(DUMP) --disassemble --reloc $(BUILD_TARGET_DIR)/image.elf > $(BUILD_TARGET_DIR)/image.lst
	$(DUMP) -h $(BUILD_TARGET_DIR)/image.elf > $(BUILD_TARGET_DIR)/image.sec
	$(DUMP) -s $(BUILD_TARGET_DIR)/image.elf > $(BUILD_TARGET_DIR)/image.cnt
	$(OBJ) -O binary $(BUILD_TARGET_DIR)/image.elf $(BUILD_TARGET_DIR)/image.bin
	$(OBJ) -R .eeprom -O ihex $(BUILD_TARGET_DIR)/image.elf $(BUILD_TARGET_DIR)/image.hex
	$(SIZE) $(BUILD_TARGET_DIR)/image.elf
	hexdump -v -e '4/1 "%02x" "\n"' $(BUILD_TARGET_DIR)/image.bin > $(BUILD_TARGET_DIR)/code.txt

## applications
# Interrupts (every image): the handlers leave interrupts disabled until the
# return of _isr (arch/riscv/hf-riscv-e/crt0.s), which returns through a5
# without saving it; dispatch() of the tick does not enable them, yield()
# restores the state of its caller and a task starts through _task_start
# (hal.c), which enables them (kernel/sched.c, lib/noc.c,
# lib/tick_release.c). The images of the runs up to r11 (A to H, CV, CV2,
# MA, W1, CF) enable interrupts inside the handlers: build them with
# -DUCX_ISR_NESTING, e.g. make weird_a_data CC="riscv64-elf-gcc
# -DUCX_ISR_NESTING" or UCX_CFLAGS=-DUCX_ISR_NESTING
# experiments/exp23/build_sw.sh (ISR_NESTING=1 in simulate.sh)
delay: rebuild
	$(CC) $(CFLAGS) -o $(BUILD_APP_DIR)/delay.o app/delay.c
	@$(MAKE) --no-print-directory link

echo: rebuild
	$(CC) $(CFLAGS) -o $(BUILD_APP_DIR)/echo.o app/echo.c
	@$(MAKE) --no-print-directory link

hello: incl ucx.pack
	$(CC) $(CFLAGS) -o $(BUILD_APP_DIR)/hello.o app/hello.c
	@$(MAKE) --no-print-directory link

# Release by tick (lib/tick_release.c): the release interrupt on every PE
# with a task counts the phases, the tick hook of the kernel (UCX_APP_TICK,
# kernel/sched.c) wakes the tasks whose phase has come, and each task of
# application E or of a generated application waits for the tick of its
# phase j + n(v) before it serves iteration j. Kernel and application are
# built with TR_DEFS. Example: make weird_a ARCH=riscv/hf-riscv-e
TR_DEFS = -DUCX_APP_IRQ4 -DUCX_APP_TICK -DUCX_TICK_RELEASE

# application E with the release by tick (app/weird_a.sim: RELEASE_MASK of
# the four PEs)
weird_a: incl
	@$(MAKE) --no-print-directory clean
	@$(MAKE) --no-print-directory ucx.pack UCX_DEFS="$(TR_DEFS)"
	$(CC) $(CFLAGS) $(TR_DEFS) -o $(BUILD_APP_DIR)/weird_a.o app/weird_a.c
	@$(MAKE) --no-print-directory link
	@find '$(SRC_DIR)' -maxdepth 1 -type f \( -name '*.pack' -o -name '*.o' \) -delete
	@find '$(BUILD_APP_DIR)' -type f -name '*.o' -delete

# application E of runs A to H (data-driven release: a task serves every
# iteration whose packets are in its queue; release of A by the kernel
# handler of PE 0); with -DUCX_ISR_NESTING (above), the image of those runs
weird_a_data: incl ucx.pack
	$(CC) $(CFLAGS) -o $(BUILD_APP_DIR)/weird_a.o app/weird_a.c
	@$(MAKE) --no-print-directory link

hello_p: incl ucx.pack
	$(CC) $(CFLAGS) -o $(BUILD_APP_DIR)/hello_preempt.o app/hello_preempt.c
	@$(MAKE) --no-print-directory link

# Applications generated by rttools.ucxgen (orca-rt-tools; app/<name>.c,
# app/<name>.json, app/<name>.sim) with the release by tick (default of the
# generator): the rule rebuilds the kernel with TR_DEFS (UCX_APP_IRQ4
# removes the handler of application E, kernel/sched.c; irq4_handler and
# the tick hook come from lib/tick_release.c). An application generated
# with --release data defines its own irq4_handler and does not link with
# these definitions. Example: make car_v ARCH=riscv/hf-riscv-e
GEN_APPS = car_v wcet_e
# composition of CAR-V and application E on the 4x5 mesh (rttools.ucxgen compose, experiments/multiapp)
GEN_APPS += carv_e
# application E alone, generated (control run of experiments/multiapp: make sim-e)
GEN_APPS += e_ucx

$(GEN_APPS): incl
	@$(MAKE) --no-print-directory clean
	@$(MAKE) --no-print-directory ucx.pack UCX_DEFS="$(TR_DEFS)"
	$(CC) $(CFLAGS) $(TR_DEFS) -o $(BUILD_APP_DIR)/$@.o app/$@.c
	@$(MAKE) --no-print-directory link
	@# the next build of another application rebuilds the kernel with the
	@# handler of E and links without this application
	@find '$(SRC_DIR)' -maxdepth 1 -type f \( -name '*.pack' -o -name '*.o' \) -delete
	@find '$(BUILD_APP_DIR)' -type f -name '*.o' -delete

# Time-triggered applications generated by rttools.ucxgen (several release
# periods, rttools/bench_t/multirate.py): the kernel calls the tick hook of
# the application before each scheduler run (UCX_APP_TICK, kernel/sched.c),
# and the NoC driver keeps the latest packet of each source without waking
# the receiver (UCX_NOC_LATEST, lib/noc.c). Example: make car_full
# ARCH=riscv/hf-riscv-e
GEN_TT_APPS = car_full
TT_DEFS = -DUCX_APP_IRQ4 -DUCX_APP_TICK -DUCX_NOC_LATEST

$(GEN_TT_APPS): incl
	@$(MAKE) --no-print-directory clean
	@$(MAKE) --no-print-directory ucx.pack UCX_DEFS="$(TT_DEFS)"
	$(CC) $(CFLAGS) $(TT_DEFS) -o $(BUILD_APP_DIR)/$@.o app/$@.c
	@$(MAKE) --no-print-directory link
	@find '$(SRC_DIR)' -maxdepth 1 -type f \( -name '*.pack' -o -name '*.o' \) -delete
	@find '$(BUILD_APP_DIR)' -type f -name '*.o' -delete

shi2010: incl ucx.pack
	$(CC) $(CFLAGS) -o $(BUILD_APP_DIR)/shi2010.o app/shi2010.c
	@$(MAKE) --no-print-directory link

mutex: rebuild
	$(CC) $(CFLAGS) -o $(BUILD_APP_DIR)/mutex.o app/mutex.c
	@$(MAKE) --no-print-directory link

cfar: incl ucx.pack
	$(CC) $(CFLAGS) -o $(BUILD_APP_DIR)/cfar.o app/cfar.c
	@$(MAKE) --no-print-directory link

dct_verify: incl ucx.pack
	$(CC) $(CFLAGS) -o $(BUILD_APP_DIR)/dct_verify.o app/dct_verify.c
	@$(MAKE) --no-print-directory link

idct_compare: incl ucx.pack
	$(CC) $(CFLAGS) -o $(BUILD_APP_DIR)/idct_compare.o app/idct_compare.c
	@$(MAKE) --no-print-directory link

noc_test: incl ucx.pack
	$(CC) $(CFLAGS) -o $(BUILD_APP_DIR)/noc_test.o app/noc_test.c
	@$(MAKE) --no-print-directory link
	
pipes: rebuild
	$(CC) $(CFLAGS) -o $(BUILD_APP_DIR)/pipes.o app/pipes.c
	@$(MAKE) --no-print-directory link

pipes_s: rebuild
	$(CC) $(CFLAGS) -o $(BUILD_APP_DIR)/pipes_small.o app/pipes_small.c
	@$(MAKE) --no-print-directory link

pipes_struct: rebuild
	$(CC) $(CFLAGS) -o $(BUILD_APP_DIR)/pipes_struct.o app/pipes_struct.c
	@$(MAKE) --no-print-directory link

prodcons: rebuild
	$(CC) $(CFLAGS) -o $(BUILD_APP_DIR)/prodcons.o app/prodcons.c
	@$(MAKE) --no-print-directory link

progress: rebuild
	$(CC) $(CFLAGS) -o $(BUILD_APP_DIR)/progress.o app/progress.c
	@$(MAKE) --no-print-directory link
	
suspend: rebuild
	$(CC) $(CFLAGS) -o $(BUILD_APP_DIR)/suspend.o app/suspend.c
	@$(MAKE) --no-print-directory link

test64: rebuild
	$(CC) $(CFLAGS) -o $(BUILD_APP_DIR)/test64.o app/test64.c
	@$(MAKE) --no-print-directory link

test_fixed: rebuild
	$(CC) $(CFLAGS) -o $(BUILD_APP_DIR)/test_fixed.o app/test_fixed.c
	@$(MAKE) --no-print-directory link

timer: rebuild
	$(CC) $(CFLAGS) -o $(BUILD_APP_DIR)/timer.o app/timer.c
	@$(MAKE) --no-print-directory link

# clean and rebuild rules
rebuild:
	find '$(BUILD_APP_DIR)' -type f -name '*.o' -delete

clean:
	find '$(BUILD_APP_DIR)' '$(BUILD_KERNEL_DIR)' -type f -name '*.o' -delete
	find '$(BUILD_TARGET_DIR)' -type f -name '*.o' -delete -o -name '*~' -delete \
		-o -name 'image.*' -delete -o -name 'code.*' -delete
	find '$(SRC_DIR)' -type f -name '*.pack' -delete 
	find '$(SRC_DIR)' -type f -name '*.o' -delete 

veryclean: clean
	echo "ARCH = none" > $(BUILD_TARGET_DIR)/target.mak
	find '$(BUILD_TARGET_DIR)' -type f -name '*.a' -delete
	rm -rf img/build*

NOC_X ?= 4
NOC_Y ?= 4

NOC_X_SEQ = $(shell seq 0 $(NOC_X))
NOC_Y_SEQ = $(shell seq 0 $(NOC_Y))

imgs.pack:
	for x in $(NOC_X_SEQ); do \
		for y in $(NOC_Y_SEQ); do \
			echo "===================================================" ; \
			echo "Generating software image for PE XY=("$$x","$$y")" ; \
			echo "==================================================="; \
			make hello_p ARCH=$$ARCH --no-print-directory NOC_X=$$x NOC_Y=$$y NOC_X_DIM=$(NOC_X) NOC_Y_DIM=$(NOC_Y); \
			mkdir -p img/build-$$x-$$y ; \
			cp -r ./build/target/* img/build-$$x-$$y ; \
			rm -rf ddma.o ; \
		done ; \
	done
	@$(MAKE) clean


# make imgs.pack NOC_Y=2 NOC_X=2 ARCH=riscv/hf-riscv-e
# make ex_hello NOC_Y=2 NOC_X=2 ARCH=riscv/hf-riscv-e
# make veryclean noc_test ARCH=riscv/hf-riscv-e
 #make veryclean shi2010 ARCH=riscv/hf-riscv-e
	

