/******************************************************************************
 * This file is part of project ORCA. More information on the project
 * can be found at the following repositories at GitHub's website.
 *
 * https://github.com/anonymous/orca-sim
 * https://github.com/anonymous/orca-software
 * https://github.com/anonymous/orca-mpsoc
 * https://github.com/anonymous/orca-tools
 * https://github.com/anonymous/orca-seer
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
#ifndef SIM_INCLUDE_SYSTEMEVENT_HPP_
#define SIM_INCLUDE_SYSTEMEVENT_HPP_

#include <inttypes.h>

#include <string>
#include <sstream>

namespace OrcaSeer::Simulation {

/**
 * Represent the many interruption request that 
 * the system can receive from its components
 */
enum class SystemEventType{
    SCHEDULER_IRQ,        // when scheduling time hits
    TASK_FINISHED_IRQ,    // when tasks requests syscall
    DEADLINE_MISSED_IRQ   // when any deadline is missed
};

/**
 * Represents an event inside a system, which usually
 * corresponds to a interruption (see <SystemEventType>).
 */
struct SystemEvent{
    uint32_t time;        // time in which the event should occur
    SystemEventType type;  // the type of the event (see SystemEventType)

    // those ctor. and dtor. are required since
    // we're going to use this into a std::queue
    SystemEvent();
    ~SystemEvent();

    SystemEvent(uint32_t time, SystemEventType type);

    bool operator<(const SystemEvent& e) const;
    bool operator==(const SystemEvent& e) const;

    std::string toString();
};

}  // namespace OrcaSeer::Simulation

#endif  // SIM_INCLUDE_SYSTEMEVENT_HPP_
