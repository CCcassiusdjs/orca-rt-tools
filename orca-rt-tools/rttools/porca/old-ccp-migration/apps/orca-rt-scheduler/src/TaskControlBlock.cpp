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
#include <TaskControlBlock.hpp>

#include <sstream>

namespace OrcaSeer::Task {

inline bool TaskControlBlock::operator==(const TaskControlBlock& b) const {
    return this->id == b.id;
}

TaskControlBlock::TaskControlBlock(uint32_t id, std::string name,
 uint32_t period, uint32_t capacity, uint32_t deadline) {
    this->id = id;
    this->name = name;
    this->period = period;
    this->capacity = capacity;
    this->deadline = deadline;

    this->current_capacity = 0;
    this->release_time = 0;
    this->next_deadline = this->deadline;
}

std::string TaskControlBlock::toString() {
    std::stringstream ss;
    ss << "[" << id << "]" << name
        << ", p:" << period
        << ", c:" << current_capacity << "/" << capacity
        << ", d:" << next_deadline << "[~" << deadline << "]";
    return ss.str();
}

}  // namespace OrcaSeer::Task
