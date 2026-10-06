from queue import PriorityQueue
from os.path import exists
from os.path import join
from os import remove


from rttools.terminal.terminal import warn, error, info, debug, header

from rttools.bench.kernel import TaskControlBlock, SystemEvent, SystemEventType
from rttools.bench.queue import PrioQueue

from rttools.gsl.graph import Graph

import random 
from math import inf


class SingleCoreEngine:
		SCHED_IRQ_PERIOD = 20
		SVG_TICK_CONST = 20
		SVG_TH_CONST = 30
		colors = []

		def __init__(
				self: "SingleCoreEngine", task_graph: Graph, algorithm: object,
				quantum: int = None
		):
				# quantum: period of the scheduler interrupt
				self._quantum = self.SCHED_IRQ_PERIOD if quantum is None else quantum
				self._trace = []    # (start, end, task) of each executed slice
				self._misses = []   # (task, absolute deadline, completion)
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


		def simulate(self: "SingleCoreEngine", time: int, trace: bool = False):
				"""Simulates until `time` or until no events are pending.

				Events: scheduler interrupt every quantum (or at the
				next release, with the processor idle) and completion of the
				running task. At each event, the engine credits the
				elapsed time to the running task and calls the scheduler."""
				self._queue = PrioQueue()
				self._queue.add(SystemEvent(self._system_time, SystemEventType.SCHEDULER_IRQ))
				iterations = 0

				while len(self._queue) > 0 and self._system_time < time:

						# remove top event from the queue
						top_event: SystemEvent = self._queue.pop()
						now = min(top_event.get_time(), time)

						# elapsed time since last event
						self._elapsed_time = now - self._system_time
						if self._running and self._elapsed_time > 0:
								self._trace.append((self._system_time, now, self._running[0]._name))
						self._system_time = now

						if self._system_time >= time:
								for t in self._running:
										t._current_capacity += self._elapsed_time
								break

						# call the scheduler
						self.schedule(self._algorithm)

						# reprogram events: drop pending ones and register the next
						# scheduler interruption and the finish of the running task
						while len(self._queue) > 0:
								self._queue.pop()

						if self._running:
								task = self._running[0]
								self._queue.add(SystemEvent(
										self._system_time + (task._capacity - task._current_capacity),
										SystemEventType.TASK_FINISHED_IRQ))
								self._queue.add(SystemEvent(
										self._system_time + self._quantum,
										SystemEventType.SCHEDULER_IRQ))
						else:
								next_release = self.get_next_release(self._blocked)
								if next_release is not None:
										self._queue.add(SystemEvent(
												max(next_release, self._system_time),
												SystemEventType.SCHEDULER_IRQ))

						if trace:
								info("iteration", iterations, "system time", self._system_time)
								self.print_task_list()
								self.log_task_list()
						iterations += 1

				return self._system_time

		def merged_trace(self: "SingleCoreEngine"):
				"""Merges consecutive slices of the same task."""
				merged = []
				for (b, e, n) in self._trace:
						if merged and merged[-1][2] == n and merged[-1][1] == b:
								merged[-1] = (merged[-1][0], e, n)
						else:
								merged.append((b, e, n))
				return merged

		def schedule(self: "SingleCoreEngine", algorithm: object):
				preempted = []
				for t in self._running:
						# add elapsed time to current capacity of the task
						t._current_capacity += self._elapsed_time

						# case A: task has not finished, preempted
						if t._current_capacity < t._capacity:
								preempted.append(t)

						# case B: task has finished; check deadline at completion
						else:
								if t._next_deadline is not None and self._system_time > t._next_deadline:
										self._misses.append((t._name, t._next_deadline, self._system_time))
										error("missed deadline!", t._name)
								if t._period is None:
										t._release_time = inf          # one-shot job
								else:
										t._release_time += t._period
										t._next_deadline += t._period
								t._current_capacity = 0
								self._blocked.append(t)

				# clear running list as tasks were added to other lists
				self._running.clear()

				# move released tasks from blocked to the ready queue
				freed = [t for t in self._blocked if t._release_time <= self._system_time]
				for t in freed:
						self._blocked.remove(t)
						self._ready.append(t)

				# preempted tasks go to the tail (after newly released ones)
				self._ready.extend(preempted)

				# sort ready list (using sort algorithm)
				self._ready = algorithm.schedule(self._ready)

				# get first element and push it to the executing queue (if any)
				if len(self._ready) != 0:
						task = self._ready.pop(0)
						self._running.append(task)

				return self._system_time

		def get_next_release(self:"SingleCoreEngine", r: list[TaskControlBlock] ):
				releases = [t._release_time for t in r if t._release_time != inf]
				return min(releases) if releases else None

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


