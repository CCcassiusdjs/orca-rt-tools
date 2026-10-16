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
#include <iostream>
#include "LeastLaxityFirst.hpp"

namespace OrcaSeer::Task
{

    LeastLaxityFirst::LeastLaxityFirst()
    {
        // add all tasks to the tlb
    }

    LeastLaxityFirst::~LeastLaxityFirst()
    {
        //
    }

    // schedule -> sort tasks
    void LeastLaxityFirst::Schedule(std::list<TaskControlBlock *> *r)
    {
        // sort list of ready tasks by latest deadline
        r->sort([](const TaskControlBlock *e1, const TaskControlBlock *e2)
                { return (e1->deadline - e1->period) < (e2->deadline - e2->period); });
    }
} // namespace OrcaSeer::Task
