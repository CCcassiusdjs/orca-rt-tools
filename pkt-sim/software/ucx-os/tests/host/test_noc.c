/* Fixes 16 to 19 (lib/noc.c).
 *
 * 16. irq3_handler: the port search did not handle k == MAX_TASKS and read
 *     pktdrv_tqueue[MAX_TASKS] (out of bounds); a port without a queue used a
 *     NULL queue.
 * 17. irq3_handler: with the queue full, it freed the packet and then read
 *     pkt->tag and woke the task (use after free).
 * 18. irq2_handler: did not check the return of ucx_malloc; with the heap
 *     exhausted, the DDMA received address 0 and wrote the packet there.
 * 19. ucx_noc_comm_create and ucx_noc_comm_destroy: error returns
 *     returned with interrupts disabled; destroy of a task without a queue
 *     dereferenced NULL. */
#include <ucx.h>
#include "host_test.h"

#define NODE 1   /* 2x2 mesh, node (1,0) */

static void setup(void)
{
	host_arena_init();
	host_ddma_map(2, 2, 1, 0);
	host_tasks_init(4);
	noc_driver_init();
	host_irq_enabled = 1;
}

/* simulates reception: irq2 (size) and irq3 (complete packet) */
static noc_packet_t *deliver(uint16_t node, uint16_t port, uint16_t tag)
{
	host_ddma_regs[8] = 4;                      /* 4 flits = 16 bytes */
	irq2_handler();
	noc_packet_t *pkt = (noc_packet_t *)(uintptr_t)host_ddma_regs[6];
	CHECK(pkt != NULL);
	if (!pkt)
		return NULL;
	pkt->source_node = 0;
	pkt->target_node = node;
	pkt->source_port = 1;
	pkt->target_port = port;
	pkt->payload_size = 4;
	pkt->tag = tag;
	host_ddma_regs[7] = host_ddma_regs[6];      /* RECV_ADDR_OUT */
	irq3_handler();
	return pkt;
}

static void test_deliver_ok(void)
{
	setup();
	host_current_task = 1;
	CHECK(ucx_noc_comm_create(5) == UCX_NOC_OK);
	deliver(NODE, 5, 77);
	CHECK(ucx_noc_probe() == 1);
	CHECK(host_counter4 == 77);
	CHECK(host_task_state(1) == TASK_READY);
	CHECK(host_irq_enabled == 1);
	noc_packet_t *p = ucx_noc_receive();
	CHECK(p && p->tag == 77);
	ucx_free(p);
}

static void test_wrong_node_dropped(void)
{
	setup();
	int live = host_live_blocks;
	deliver(3, 5, 10);
	CHECK(host_live_blocks == live);
	CHECK(host_irq_enabled == 1);
}

static void test_unbound_port_dropped(void)          /* 16 */
{
	setup();
	host_current_task = 1;
	CHECK(ucx_noc_comm_create(5) == UCX_NOC_OK);
	int live = host_live_blocks;
	host_counter4 = 0;
	deliver(NODE, 9, 42);                        /* no task on port 9 */
	CHECK(host_live_blocks == live);             /* packet freed */
	CHECK(host_counter4 == 0);
	CHECK(host_task_state(0) != TASK_READY);
	CHECK(host_irq_enabled == 1);
}

static void test_queue_full_no_use_after_free(void)  /* 17 */
{
	setup();
	host_current_task = 1;
	CHECK(ucx_noc_comm_create(5) == UCX_NOC_OK);
	for (int i = 0; i < MAX_PKT_QUEUE_SLOTS; i++)
		deliver(NODE, 5, 100 + i);
	CHECK(ucx_noc_probe() == MAX_PKT_QUEUE_SLOTS);
	int live = host_live_blocks;
	deliver(NODE, 5, 999);                       /* queue full */
	CHECK(ucx_noc_probe() == MAX_PKT_QUEUE_SLOTS);
	CHECK(host_live_blocks == live);             /* packet discarded and freed */
	CHECK(host_counter4 == 100 + MAX_PKT_QUEUE_SLOTS - 1);
	CHECK(host_irq_enabled == 1);
}

static void test_irq2_malloc_failure(void)           /* 18 */
{
	setup();
	host_current_task = 1;
	CHECK(ucx_noc_comm_create(5) == UCX_NOC_OK);
	int live = host_live_blocks;
	host_ddma_regs[6] = 0;
	host_ddma_regs[8] = 4;
	host_fail_next_malloc = 1;
	irq2_handler();
	CHECK(host_ddma_regs[6] != 0);               /* DDMA does not receive address 0 */
	CHECK(host_irq_enabled == 1);
	/* the packet arrives in the discard buffer and irq3 discards it */
	noc_packet_t *pkt = (noc_packet_t *)(uintptr_t)host_ddma_regs[6];
	if (pkt) {
		pkt->target_node = NODE;
		pkt->target_port = 5;
		pkt->tag = 5;
		host_ddma_regs[7] = host_ddma_regs[6];
		irq3_handler();
	}
	CHECK(ucx_noc_probe() == 0);
	CHECK(host_live_blocks == live);
	CHECK(host_irq_enabled == 1);
}

static void test_comm_create_errors_restore_irq(void)  /* 19 */
{
	setup();
	host_current_task = 1;
	CHECK(ucx_noc_comm_create(5) == UCX_NOC_OK);
	CHECK(host_irq_enabled == 1);
	CHECK(ucx_noc_comm_create(6) == UCX_NOC_TASK_BIND_ALREADY);
	CHECK(host_irq_enabled == 1);
	host_current_task = 2;
	CHECK(ucx_noc_comm_create(5) == UCX_NOC_PORT_BIND_ALREADY);
	CHECK(host_irq_enabled == 1);
	host_current_task = 3;
	host_fail_next_malloc = 1;
	CHECK(ucx_noc_comm_create(7) == UCX_NOC_OUT_OF_MEMORY);
	CHECK(host_irq_enabled == 1);
}

static void test_comm_destroy(void)                  /* 19 */
{
	setup();
	host_current_task = 3;
	CHECK(ucx_noc_comm_destroy(7) == (uint32_t)UCX_NOC_TASK_NOT_BOUND);
	CHECK(host_irq_enabled == 1);
	host_current_task = 1;
	CHECK(ucx_noc_comm_create(5) == UCX_NOC_OK);
	deliver(NODE, 5, 1);
	CHECK(ucx_noc_comm_destroy(5) == (uint32_t)UCX_NOC_OK);
	CHECK(host_irq_enabled == 1);
	host_current_task = 2;
	CHECK(ucx_noc_comm_create(5) == UCX_NOC_OK);  /* port released */
}

/* review: local send (same node) only considers ports with an open queue */
static void test_local_send_bound_port(void)
{
	setup();
	host_current_task = 1;
	CHECK(ucx_noc_comm_create(0) == UCX_NOC_OK);   /* port 0 */
	host_current_task = 2;
	noc_packet_t *p = ucx_noc_create_packet(4);
	CHECK(p != NULL);
	CHECK(ucx_noc_send(NODE, 0, p, 33) == 0);
	host_current_task = 1;
	CHECK(ucx_noc_probe() == 1);
	CHECK(host_task_state(1) == TASK_READY);
	CHECK(host_counter4 == 33);
	CHECK(host_irq_enabled == 1);
}

int main(void)
{
	RUN_FORK(test_deliver_ok);
	RUN_FORK(test_wrong_node_dropped);
	RUN_FORK(test_unbound_port_dropped);
	RUN_FORK(test_queue_full_no_use_after_free);
	RUN_FORK(test_irq2_malloc_failure);
	RUN_FORK(test_comm_create_errors_restore_irq);
	RUN_FORK(test_comm_destroy);
	RUN_FORK(test_local_send_bound_port);
	DONE();
}
