from queue import PriorityQueue
from os.path import exists
from os.path import join
from os import remove


from rttools.terminal.terminal import warn, error, info, debug, header

from rttools.bench.kernel import TaskControlBlock, SystemEvent, SystemEventType
from rttools.bench.queue import PrioQueue

from rttools.gsl.graph import Graph

import random 


class SingleCoreEngine:
		SCHED_IRQ_PERIOD = 20
		SVG_TICK_CONST = 20
		SVG_TH_CONST = 30
		colors = []

		def __init__(
				self: "SingleCoreEngine", task_graph: Graph, algorithm: object
		):
				self._system_time: int = 0
				self._queue = PrioQueue()
				self._running = []
				self._blocked = []
				self._ready = []

				# populate blocked list with tasks from the graph; nodes carry
				# wcet and, optionally, period and deadline. A node without
				# period is a one-shot job (released once at time 0).
				for n in task_graph._nodes:
					data = n._data
					wcet = int(data["wcet"])
					period = int(data["period"]) if "period" in data else None
					deadline = int(data["deadline"]) if "deadline" in data else period
					tlb = TaskControlBlock(n._id, data["label"], period, wcet, deadline)
					self._blocked.append(tlb)

				self._algorithm = algorithm


				def printrunning(self: "SingleCoreEngine"):
						for t in self._running:
								print(f"RUNNING - id {t._id} current {t._current_capacity} capa {t._capacity}")
				def printready(self: "SingleCoreEngine"):
						for t in self._ready:
								print(f"READY - id {t._id} current {t._current_capacity} capa {t._capacity}")
				def printblocked(self: "SingleCoreEngine"):
						for t in self._blocked:
								print(f"BLOCKED - id {t._id} current {t._current_capacity} capa {t._capacity}")


		def simulate(self: "SingleCoreEngine", time: int, trace: bool):

				# add an schedule event to the simulation queue				
				irq_event: SystemEvent = SystemEvent(0, SystemEventType.SCHEDULER_IRQ)
				self._queue.add(irq_event)

				# reset simulation stats 
				iterations = 0
				start_time = 0

				# simulate until timeout	
				while self._system_time < time: 
						
						# remove top event from the queue 
						top_event: SystemEvent = self._queue.pop()

						# update event next release time and push it back to the queue
						self._elapsed_time = top_event._time - self._system_time
						self._system_time += self._elapsed_time
						
						# print event information (tasks or schedule)
						if top_event._type == SystemEventType.TASK_FINISHED_IRQ:
								warn(str(self._system_time) + ": task finished")
						else:
								# return the scheduler to the simulation timeline
								warn(str(self._system_time) + ": scheduled irq")
								top_event._time = top_event._time + SystemEventType.SCHEDULER_IRQ
								self._queue.push(top_event)

								# calls the scheduler 
								


						# call the scheduler 
						self.schedule(self._algorithm)
						

						# Next event is the scheduler interruption

						if top_event.get_type() == SystemEventType.SCHEDULER_IRQ:
								# remove all events from the simulation queue; since the
								# scheduler_irq has been removed, only the event for the
								# running task remains
								while self._queue.__len__() > 0:
										self._queue.pop()
							 
								# register the interruption                
								if len(self._ready)==0:
										irq_event._time = self._system_time + (self.get_next_release(self._blocked) - self._system_time)
								else:
										irq_event._time = self._system_time + self.SCHED_IRQ_PERIOD
								self._queue.add(irq_event)

						# register next task finish within the simulation
						if len(self._running)==0:
								next_task = None
						else:
								next_task = self._running[0]

						info(iterations, start_time, self._system_time, self._system_time)
						start_time = self._system_time
						iterations += 1
						
						# slack timeclear
						if next_task is not None:
								top_event._time = self._system_time + (
										 next_task._capacity - next_task._current_capacity
								)
								
								top_event.type = SystemEventType.TASK_FINISHED_IRQ
								self._queue.add(top_event)
								warn("running task")

								# info(
								#     iterations,
								#     next_task._period,
								#     next_task._capacity,
								#     next_task._deadline,
								# )
						else:
								warn("slack time")
						
						info("system time", self._system_time)
						self.print_task_list()
						#self.log_tasks()
						self.svg_append(self._running,time)
						#self.svg_print(time)
						self.log_task_list()
						
				return self._system_time

		def schedule(self: "SingleCoreEngine", algorithm: object):
				for t in self._running:
						# add elapsed time to current capacity of the task
						t._current_capacity += self._elapsed_time
						 
						# case A: task has timed out, preempted
						if t._current_capacity < t._capacity:
								self._ready.append(t)

						# case B: task has finished succeffuly
						else:
								t._release_time += t._period
								t._current_capacity = 0
								t._next_deadline += t._period
								self._blocked.append(t)

				# clear running list as tasks were added to other lists
				self._running.clear()

				freed = []

				# move tasks from blocked to the ready queue
				for t in self._blocked:
						if t._release_time <= self._system_time:
								self._ready.append(t)
								freed.append(t)

				# remove freed tasks from blocked list
				for t in freed:
						self._blocked.remove(t)

				# sort ready list (using sort algorithm)
				self._ready = self._algorithm.schedule(self._ready)

				# get first element and push it to the executing queue (if any)
				if len(self._ready) != 0:
						task = self._ready[0]
						self._ready.remove(task)
						self._running.append(task)

						if task._next_deadline < self._system_time:
								error("missed deadline!",task._id)

				return self._system_time

		def get_next_release(self:"SingleCoreEngine", r: list[TaskControlBlock] ):
				r = sorted(r, key = lambda e: e._release_time, reverse = False)
				aux = r[0]._release_time
				# print("*********************8")
				# print(aux)
				return aux

		def print_task_list(self: "SingleCoreEngine"):
				info("==============================================")
				info("----- running")
				for t in self._running:
						info(str(t))

				info("----- ready")
				for t in self._ready:
						info(str(t))

				info("----- blocked")
				for t in self._blocked:
						info(str(t))

				info("==============================================")


		
		def log_task_list(self: "SingleCoreEngine"):

				#log("==============================================")
				print ("----- running")
				for t in self._running:
						print(t.str_log())

				print("----- ready")
				for t in self._ready:
						print(t.str_log())

				print("----- blocked")
				for t in self._blocked:
						print(t.str_log())

				print("==============================================")
				

		def log_tasks(self: "SingleCoreEngine"):
				filename = 'rtbench/data_out/aa.txt'
				

				#print("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
				

				log_out = open(filename, 'a')
				log_out.write("=====================\n")
				blocked_text = f'blocked {self._system_time}\n'
				log_out.write(blocked_text)


				for t in self._blocked:
						data = f'{str(t)} \n'

						logText = f'{t._id} {t._name} {t._current_capacity} {t._capacity} {t._next_deadline} {t._deadline} \n'

						log_out.write(logText)

				ready_text = f'ready {self._system_time}\n'
				log_out.write(ready_text)
				for t in self._ready:
						data2 = f'{str(t)} \n'
						log_out.write(data2)

				
				running_text = f'running {self._system_time}\n'
				log_out.write(running_text)
				for t in self._running:
						data3 = f'{str(t)} \n'
						log_out.write(data3)
				log_out.write("=====================\n")


				
		
		
		def svg_append(self:"SingleCoreEngine",r:list[TaskControlBlock],time:int):
				filename = 'rtbench/data_out/taskgraph.svg'
				if not exists(filename):
						svg_init(time)
				svg_out = open(filename,'a')
				if(self._system_time>=time):
						self.svg_end(time)
						return
				for t in r:
						print()
						#color = get_color(t._id)
						taskRect = f'<rect x="{self._system_time*self.SVG_TICK_CONST+1}" y="{(t._id-1)*30+1}" width="{t._capacity*self.SVG_TICK_CONST}" height="30" fill="{self.colors[t._id-1]}"/>\n' 
						svg_out.write(taskRect)
				
		def svg_end(self:"SingleCoreEngine",time):
				filename = 'rtbench/data_out/taskgraph.svg'
				if not exists(filename):
						return
				else:
						svg_out = open(filename,'a')
						ticksX = '\n'
						#creating the dots of the graph
						for i in range(0,time):
								#rotated caption ticks
								ticksX += f'<text x="{self.SVG_TICK_CONST +i*self.SVG_TICK_CONST +4 }" y="-15" font-size="11"  transform="rotate(-90,{self.SVG_TICK_CONST +i*self.SVG_TICK_CONST},-20 )" text-anchor="end">{i+1}</text>\n'
								#ticks
								ticksX += f'<rect x="{self.SVG_TICK_CONST+i*self.SVG_TICK_CONST}" y="-5" width="1" height="10" fill="black"/>\n'

						svg_out.write(ticksX)
						#closing the svg file
						svg_out.write('</svg>')
				svg_out.close()

		


		def setColors(self:"SingleCoreEngine"):
				r = lambda: random.randint(0, 220)
				for t in range(0,len(self._blocked)):
						self.colors.append("#{:02x}{:02x}{:02x}".format(r(), r(), r()))
				return


