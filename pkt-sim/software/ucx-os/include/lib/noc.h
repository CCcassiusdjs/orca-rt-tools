// TODO: 
#define MAX_TASKS 16

// configs
#define MAX_PKT_QUEUE_SLOTS 8

// error messages
#define UCX_NOC_TASK_BIND_ALREADY (-1)
#define UCX_NOC_PORT_BIND_ALREADY (-2)
#define UCX_NOC_OUT_OF_MEMORY     (-3)
#define UCX_NOC_OK                (-4)
#define UCX_NOC_UNABLE_TO_DESTROY (-5)
#define UCX_NOC_TASK_NOT_BOUND    (-6)
#define UCX_NOC_PORT_HAS_NO_TASK  (-7)
#define UCX_NOC_WUT               (-99)


typedef struct {
  uint16_t source_node;  // source and destination node, integer identifiers
  uint16_t target_node;
  uint16_t source_port;  // source and target ports
  uint16_t target_port;
  uint16_t payload_size; // size of the payload
  uint16_t tag;          // tag, used to filter packets at the application level
  uint8_t  data[];       //payload
} noc_packet_t;

/**
 * Driver initialization routine. Sets up a queue of packets 
 * and resets an associative array connecting ports to cpus.
*/
void noc_driver_init(void);

/**
 * Called whenever a new packet arrives from the network
 * (interruption handler).
*/
void noc_driver_recv_isr();
void noc_driver_send_ack_isr();

/**
 * Returns the ID of the cpu (unsigned integers, starts 
 * from zero, unique per cpu).
*/
uint32_t ucx_noc_cpu_id(void);

/**
 * Sends a packet through the network.
 * 
 * @target_cpu: destination cpu id
 * @target_port: destination port number
 * @pkt: a pointer to the packet to be sent
 * @tag: an optional field used to filter packets
*/
uint32_t ucx_noc_send(uint16_t target_cpu, uint16_t target_port, noc_packet_t* pkt, uint16_t tag);

/**
 * Create a new packet and returns a pointer to it. Must inform
 * the number of bytes in the payload.
*/
noc_packet_t* ucx_noc_create_packet(uint32_t size);

/**
 * Bind a task to a port to send and receive packets.
*/
int32_t ucx_noc_comm_create(uint16_t port);

/**
 * REmove port binding from task
*/
uint32_t ucx_noc_comm_destroy(uint16_t port);


noc_packet_t* ucx_noc_receive();

int32_t ucx_noc_probe(void);

void irq1_handler(void);
void irq2_handler(void);




