/* Reception and ports of lib/noc.c.
 *
 * 1. irq3_handler: a packet for a port without a queue (search ends at
 *    k == MAX_TASKS) is dropped; no access beyond pktdrv_tqueue.
 * 2. irq3_handler: with the queue full, the packet is freed and not read
 *    again (the tag counter keeps the tag of the last queued packet).
 * 3. irq2_handler: when ucx_malloc fails, the DDMA receives the address of
 *    a discard buffer (never address 0) and irq3_handler drops the packet.
 * 4. ucx_noc_comm_create and ucx_noc_comm_destroy: every return restores
 *    the interrupts; destroy of a task without a queue returns
 *    UCX_NOC_TASK_NOT_BOUND.
 * 5. irq2_handler and irq3_handler leave interrupts disabled until the
 *    return of _isr (host_isr); with -DUCX_ISR_NESTING (test_noc_nesting
 *    of run.sh) both enable them before that return. */
#include <ucx.h>
#include "host_test.h"

void irq3_handler(void);

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
	host_isr(irq2_handler);
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
	host_isr(irq3_handler);
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

static void test_unbound_port_dropped(void)          /* 1 */
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

static void test_queue_full_no_use_after_free(void)  /* 2 */
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

static void test_irq2_malloc_failure(void)           /* 3 */
{
	setup();
	host_current_task = 1;
	CHECK(ucx_noc_comm_create(5) == UCX_NOC_OK);
	int live = host_live_blocks;
	host_ddma_regs[6] = 0;
	host_ddma_regs[8] = 4;
	host_fail_next_malloc = 1;
	host_isr(irq2_handler);
	CHECK(host_ddma_regs[6] != 0);               /* DDMA does not receive address 0 */
	CHECK(host_irq_enabled == 1);
	/* the packet arrives in the discard buffer and irq3 discards it */
	noc_packet_t *pkt = (noc_packet_t *)(uintptr_t)host_ddma_regs[6];
	if (pkt) {
		pkt->target_node = NODE;
		pkt->target_port = 5;
		pkt->tag = 5;
		host_ddma_regs[7] = host_ddma_regs[6];
		host_isr(irq3_handler);
	}
	CHECK(ucx_noc_probe() == 0);
	CHECK(host_live_blocks == live);
	CHECK(host_irq_enabled == 1);
}

static void test_comm_create_errors_restore_irq(void)  /* 4 */
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

static void test_comm_destroy(void)                  /* 4 */
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

/* local send (same node) only considers ports with an open queue */
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

static void test_handlers_leave_interrupts_disabled(void)  /* 5 */
{
	setup();
	host_current_task = 1;
	CHECK(ucx_noc_comm_create(5) == UCX_NOC_OK);
	host_isr_nested = 0;
	deliver(NODE, 5, 12);
	CHECK(ucx_noc_probe() == 1);
	CHECK(host_irq_enabled == 1);               /* after the return of _isr */
#ifdef UCX_ISR_NESTING
	CHECK(host_isr_nested == 2);
#else
	CHECK(host_isr_nested == 0);
#endif
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
	RUN_FORK(test_handlers_leave_interrupts_disabled);
	DONE();
}
