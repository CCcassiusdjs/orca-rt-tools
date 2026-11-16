#!/bin/sh
# Builds wcet_bodies.c into wcet_bodies.elf, wcet_bodies.lst and
# wcet_bodies.hex (one word per line, the format of cpu_cycles.hex and of
# code.txt of the ucx-os build). CC defaults to riscv64-elf-gcc (the
# toolchain of the paper, 12.2.0); the stored image comes from the CC that
# wcet_bodies.txt names.
set -e
T=$(cd "$(dirname "$0")" && pwd)
CC=${CC:-riscv64-elf-gcc}
PFX=${CC%gcc}
OUT=${OUT:-$T}
cat > "$OUT/wcet_bodies.ld" <<'LD'
SECTIONS
{
	. = 0;
	.text : { *(.text.start) *(.text .text.*) }
	.rodata : { *(.rodata .rodata.* .srodata .srodata.*) }
	.data : { *(.data .data.* .sdata .sdata.*) }
	.bss : { *(.bss .bss.* .sbss .sbss.*) }
}
LD
"$CC" -march=rv32e -mabi=ilp32e -O2 -Wall -ffreestanding -nostdlib -mstrict-align \
	-I"$T/../../software/ucx-os/include" -T "$OUT/wcet_bodies.ld" -o "$OUT/wcet_bodies.elf" "$T/wcet_bodies.c"
"${PFX}objdump" --disassemble -Mno-aliases "$OUT/wcet_bodies.elf" > "$OUT/wcet_bodies.lst"
"${PFX}objcopy" -O binary "$OUT/wcet_bodies.elf" "$OUT/wcet_bodies.bin"
hexdump -v -e '4/1 "%02x" "\n"' "$OUT/wcet_bodies.bin" > "$OUT/wcet_bodies.hex"
rm -f "$OUT/wcet_bodies.bin" "$OUT/wcet_bodies.ld"
"$CC" --version | head -1 > "$OUT/wcet_bodies.txt"
