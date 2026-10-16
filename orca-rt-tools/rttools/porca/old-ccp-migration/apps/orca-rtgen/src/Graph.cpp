/******************************************************************************
 * This file is part of project ORCA. More information on the project
 * can be found at the following repositories at GitHub's website.
 *
 * https://github.com/anonymous/orca-sim
 * https://github.com/anonymous/orca-software
 * https://github.com/anonymous/orca-mpsoc
 * https://github.com/anonymous/orca-tools
 * https://github.com/anonymous/orca-modeling
 *
 * Copyright (C) 2018-2020 Anonymous Author, <anonymous@example.org>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with this program; if not, write to the Free Software Foundation, Inc.,
 * 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA. 
******************************************************************************/
#include <list>
#include <sstream>

#include "Graph.hpp"
#include "GraphEdge.hpp"
#include "GraphNode.hpp"

namespace Orca::RTGen {

Graph::Graph() {
    edges = new std::list<GraphEdge*>();
    nodes = new std::list<GraphNode*>();
    data = nullptr;
}

int Graph::addNode(GraphNode* node) {
    nodes->push_back(node);
    return 0;
}

int Graph::removeNode(GraphNode* node) {
	nodes->remove(node);
    return 0;
}

int Graph::addEdge(GraphEdge* edge) {

	char mark = 0;

    std::list<GraphNode*>::iterator i, j;

    for (i = nodes->begin(), j = nodes->end(); i != j; i++) {

    	// found source in graph's node list, raise first bit flag "0000 0001"
    	if (*i == edge->getTo()) mark |= 0x1;

    	// found target in graph's node list, raise second bit flag "0000 0010"
        if (*i == edge->getFrom()) mark |= 0x2;

        // if both nodes were found ("0000 0011" is equals to 0x3), add edge to the graph
        if (mark == 0x3) {
            edges->push_back(edge);
            return 0;
        }
    }

    return 1;
}

Graph::~Graph() {
	// nothing to do here
}


std::list<GraphNode*>* Graph::getNodes() {
    return nodes;
}

std::list<GraphEdge*>* Graph::getEdges() {
    return edges;
}

GraphData* Graph::getData() {
	return this->data;
}

}  // namespace Orca::RTGen
