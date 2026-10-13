# this is stuff specific to this architecture
ARCH_DIR = $(SRC_DIR)/arch/$(ARCH)
INC_DIRS = -I $(ARCH_DIR)

# core speed
#F_CLK = 25000000
# 1MHz?
#F_CLK = 1000000
#F_CLK = 2400000
#F_CLK = 2500000
#F_CLK = 1000000000
#F_CLK = 1000000000
#F_CLK = 500000000
#F_CLK = 1000000
F_CLK = 500000000


# uart baud rate
SERIAL_BAUDRATE = 57600

# timer interrupt frequency (100 -> 100 ints/s -> 10ms tick time. 0 -> timer0 fixed frequency)
#F_TICK = 10
#F_TICK = 1000000
F_TICK = 2000

# extra definitions for every object (empty by default; the generated
# applications of the Makefile pass UCX_DEFS=-DUCX_APP_IRQ4)
UCX_DEFS ?=

# remove unreferenced functions
CFLAGS_STRIP = -fdata-sections -ffunction-sections
LDFLAGS_STRIP = --gc-sections

# this is stuff used everywhere - compiler and flags should be declared (ASFLAGS, CFLAGS, LDFLAGS, LD_SCRIPT, CC, AS, LD, DUMP, READ, OBJ and SIZE).
ASFLAGS = -march=rv32e -mabi=ilp32e #-fPIC
CFLAGS = -Wall -march=rv32e -mabi=ilp32e -O2 -c -mstrict-align -ffreestanding -nostdlib -ffixed-a5 $(INC_DIRS) -DF_CPU=${F_CLK} -D USART_BAUD=$(SERIAL_BAUDRATE) -DF_TIMER=${F_TICK} -DLITTLE_ENDIAN $(CFLAGS_STRIP) -DDEBUG_PORT $(UCX_DEFS) #-mrvc -fPIC 
ARFLAGS = r

LDFLAGS = -melf32lriscv $(LDFLAGS_STRIP)
LDSCRIPT = $(ARCH_DIR)/hf-risc.ld

CC = riscv64-elf-gcc
AS = riscv64-elf-as
LD = riscv64-elf-ld
DUMP = riscv64-elf-objdump -Mno-aliases
READ = riscv64-elf-readelf
OBJ = riscv64-elf-objcopy
SIZE = riscv64-elf-size
AR = riscv64-elf-ar

HAL_SRC = $(ARCH_DIR)/hal.c \
		$(ARCH_DIR)/interrupt.c \
		$(ARCH_DIR)/../../common/muldiv.c

crt0.o: $(ARCH_DIR)/crt0.s
	$(AS) $(ASFLAGS) -o crt0.o $(ARCH_DIR)/crt0.s

hal.pack: crt0.o $(HAL_SRC)
	$(CC) $(CFLAGS) $(HAL_SRC)
	echo null > hal.pack

