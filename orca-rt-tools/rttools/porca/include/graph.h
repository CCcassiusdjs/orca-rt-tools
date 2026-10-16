#include <vector>

struct graph_node {
    int id;
    void* data;
};

struct graph_edge {
    int id;
    graph_node* source;
    graph_node* target;
    void* data;
};

struct graph {
    std::vector<graph_node>* nodes;
    std::vector<graph_edge>* edges;
};