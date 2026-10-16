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
#ifndef ORCA_RTGEN_GRAPH_HPP_
#define ORCA_RTGEN_GRAPH_HPP_

#include <list>
#include <string>

#include "GraphEdge.hpp"
#include "GraphNode.hpp"
#include "GraphData.hpp"

namespace Orca::RTGen {

class Graph{
 private:
    std::list<GraphEdge*>* edges;
    std::list<GraphNode*>* nodes;
    GraphData* data;

 public:
    Graph();
    ~Graph();

    void setData(GraphData* dataptr);
    GraphData* getData();

    int addNode(GraphNode* node);
    int addEdge(GraphEdge* edge);

    int removeNode(GraphNode* node);

    std::list<GraphNode*>* getNodes();
    std::list<GraphEdge*>* getEdges();
};

}  // namespace Orca::RTGen

#endif  // ORCA_RTGEN_GRAPH_HPP_
