/* Fix 15 (device/ddma.c): DDMA address conversions.
 *
 * Linear node address: a = y * DIMX + x (the same one _ddma_atox uses,
 * a % DIMX). Defeitos:
 *   _ddma_node_addr: Y * DIMY + X  (correct: Y * DIMX + X)
 *   _ddma_atoy:      a / DIMY      (correct: a / DIMX)
 *   _ddma_xyta:      (x << 8) & y  (correct: (x << 8) | y)
 * In a square mesh (2x2) the first two do not show up; in 3x2 they do. */
#include <ucx.h>
#include "host_test.h"

uint32_t _ddma_atox(uint32_t addr);
uint32_t _ddma_atoy(uint32_t addr);
uint32_t _ddma_xyta(uint32_t x, uint32_t y);

static void test_node_addr_3x2(void)
{
	host_ddma_map(3, 2, 2, 1);          /* node (2,1) in a 3x2 mesh */
	CHECK(_ddma_node_addr() == 5);
}

static void test_atox_atoy_3x2(void)
{
	host_ddma_map(3, 2, 0, 0);
	for (uint32_t y = 0; y < 2; y++)
		for (uint32_t x = 0; x < 3; x++) {
			uint32_t a = y * 3 + x;
			CHECK(_ddma_atox(a) == x);
			CHECK(_ddma_atoy(a) == y);
		}
}

static void test_xyta(void)
{
	CHECK(_ddma_xyta(2, 1) == 0x0201);
	CHECK(_ddma_xyta(0, 3) == 0x0003);
	CHECK(_ddma_xyta(4, 0) == 0x0400);
}

static void test_send_registers(void)
{
	host_ddma_map(3, 2, 0, 0);
	uint32_t payload[4];
	_ddma_send(4, 10, payload);          /* node 4 = (1,1); 10 bytes = 3 flits */
	CHECK(host_ddma_regs[1] == 0x0101);
	CHECK(host_ddma_regs[3] == 3);
	CHECK(host_ddma_regs[4] == 1);
}

static void test_square_mesh_unchanged(void)
{
	host_ddma_map(2, 2, 1, 1);
	CHECK(_ddma_node_addr() == 3);
	CHECK(_ddma_atox(3) == 1 && _ddma_atoy(3) == 1);
}

/* zero-size packet: a size flit of 0 corrupts the Hermes port
 * (Hermes_buffer.vhd reads the next flit as the size); the driver refuses */
static void test_send_zero_size_rejected(void)
{
	host_ddma_map(2, 2, 0, 0);
	uint32_t payload[1];
	CHECK(_ddma_send(1, 0, payload) != 0);
	CHECK(host_ddma_regs[4] == 0);          /* command not triggered */
}

int main(void)
{
	host_arena_init();
	RUN(test_node_addr_3x2);
	RUN(test_atox_atoy_3x2);
	RUN(test_xyta);
	RUN(test_send_registers);
	RUN(test_square_mesh_unchanged);
	RUN(test_send_zero_size_rejected);
	DONE();
}
