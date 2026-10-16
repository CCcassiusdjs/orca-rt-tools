/*
 * Program of tb_cpu_trace.vhd: the bodies of the applications of
 * rttools.ucxgen --bodies (sort, search, count; the functions of
 * orca-rt-tools/rttools/ucxgen/emit.py, WORK_BODY, with WORK_N = 64 and
 * COUNT_MAX = 256) on inputs that take different paths: a descending array
 * (most shifts of the insertion sort), an ascending array (fewest), a key
 * that the search does not find (all words), a key in the first word, the
 * largest count, and xorshift32 arrays.
 *
 * Each wrapper m_<body> writes the marker 2b - 1, calls the body and
 * writes 2b (b = 1 sort, 2 search, 3 count) to 0x2000002C; the program ends
 * with a store to 0x20000030. tb_cpu_trace.vhd prints the cycle of each
 * marker; orca-rt-tools/tests/test_wcet_rtl.py compares the cycles between
 * the markers of each call with the static WCET of the wrapper and of the
 * body (rttools.wcet on wcet_bodies.elf).
 *
 * Build: build_wcet_bodies.sh (riscv64-elf-gcc or CC; -march=rv32e
 * -mabi=ilp32e -O2, image from address 0, stack at 64 KiB).
 */
#include <stdint.h>
#include "lib/wcet.h"

#define WORK_N    64
#define COUNT_MAX 256
#define TESTS     12

#define MARK (*(volatile uint32_t *)0x2000002Cu)
#define DONE (*(volatile uint32_t *)0x20000030u)

__asm__(".section .text.start,\"ax\",@progbits\n"
	".globl _start\n"
	"_start:\n"
	"\tlui sp, 0x10\n"
	"\tjal ra, main\n"
	"1:\tj 1b\n"
	".previous\n");

static uint32_t work[WORK_N];
volatile uint32_t sink;

static void fill(uint32_t *w, uint32_t k, uint32_t port)
{
	uint32_t x = (k << 8) ^ port ^ 0x9E3779B9u;

	for (int i = 0; i < WORK_N; i++) {
		WCET_LOOP_BOUND(WORK_N);
		x ^= x << 13;
		x ^= x >> 17;
		x ^= x << 5;
		w[i] = x;
	}
}

static __attribute__((noinline)) void body_sort(uint32_t *w)
{
	for (int i = 1; i < WORK_N; i++) {
		WCET_LOOP_BOUND(WORK_N);
		uint32_t x = w[i];
		int j = i;

		while (j > 0 && w[j - 1] > x) {
			WCET_LOOP_TOTAL(WORK_N * (WORK_N - 1) / 2 + WORK_N - 1);
			w[j] = w[j - 1];
			j--;
		}
		w[j] = x;
	}
}

static __attribute__((noinline)) int body_search(const uint32_t *w, uint32_t key)
{
	for (int i = 0; i < WORK_N; i++) {
		WCET_LOOP_BOUND(WORK_N);
		if ((w[i] & 0xFF) == key)
			return i;
	}
	return -1;
}

static __attribute__((noinline)) void body_count(uint32_t *w)
{
	uint32_t c = (w[0] & (COUNT_MAX - 1)) + 1;
	uint32_t acc = w[1];

	for (uint32_t i = 0; i < c; i++) {
		WCET_LOOP_BOUND(COUNT_MAX);
		acc = (acc << 3) ^ (acc >> 5) ^ w[i & (WORK_N - 1)];
	}
	w[1] = acc;
}

__attribute__((noinline)) void m_sort(uint32_t *w)
{
	MARK = 1;
	body_sort(w);
	MARK = 2;
}

__attribute__((noinline)) void m_search(uint32_t *w, uint32_t key)
{
	MARK = 3;
	sink = (uint32_t)body_search(w, key);
	MARK = 4;
}

__attribute__((noinline)) void m_count(uint32_t *w)
{
	MARK = 5;
	body_count(w);
	MARK = 6;
}

int main(void)
{
	for (uint32_t t = 0; t < TESTS; t++) {
		fill(work, t + 1, 7);
		if (t == 0)
			for (int i = 0; i < WORK_N; i++)
				work[i] = WORK_N - i;
		if (t == 1)
			for (int i = 0; i < WORK_N; i++)
				work[i] = i;
		m_sort(work);

		fill(work, t + 1, 9);
		m_search(work, t == 0 ? 0x100 : (t == 1 ? (work[0] & 0xFF) : (work[0] >> 24)));

		fill(work, t + 1, 11);
		if (t == 0)
			work[0] = COUNT_MAX - 1;
		if (t == 1)
			work[0] = 0;
		m_count(work);
	}
	DONE = 1;
	for (;;)
		;
}
