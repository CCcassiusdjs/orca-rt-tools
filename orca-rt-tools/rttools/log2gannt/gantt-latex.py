from sys import argv

KERNEL_SCHED_TIME = 200

task_names = {
	"0-0": ['IDLE', 'F', 'D', 'B', 'A'],
	"1-1": ['IDLE', 'J', 'G'],
	"0-1": ['IDLE', 'C'],
	"1-0": ['IDLE', 'H', 'I', 'E']
}

pkts = {
	1230 : {"source": "A", "target": "C"},
	4560 : {"source": "A", "target": "B"},
	7890 : {"source": "B", "target": "D"},
	1200 : {"source": "C", "target": "E"},
	3450 : {"source": "D", "target": "F"},
	6780 : {"source": "F", "target": "G"},
	9010 : {"source": "E", "target": "I"},
	2340 : {"source": "E", "target": "H"},
	5670 : {"source": "I", "target": "J"},
	8900 : {"source": "H", "target": "J"},
	1230 : {"source": "G", "target": "J"}
}

def f2na(flit_addr):
	addr = int(flit_addr, 16)
	x = (addr >> 8) & 0xFF   # address: (x << 8) | y
	y = addr & 0xFF
	return f"{x}-{y}"

def main(argv):
	
	lines = []
	with open(argv[0]) as f:
		lines = f.readlines()

	# parse scheduling events
	lines = [x.replace("\n","").replace("#", "").strip() for x in lines]
	lines = [x for x in lines if x.find("Elapsed") < 0]
	lines = [x for x in lines if len(x) > 0]

	lines_sched = [x for x in lines if x.find("scheduled") >= 0]
	lines_sched = [x.split(" ") for x in lines_sched]
	lines_sched = [{"time": int(x[0]), "node": x[1], "task": task_names[x[1]][int(x[3])]} for x in lines_sched]

	# parse net events
	lines_recv = [x for x in lines if x.find("<-") >= 0]
	lines_recv = [x.split(" ") for x in lines_recv]
	lines_recv = [{"time": int(x[0]), "node": x[1], "tag": x[4], "s": "recv"} for x in lines_recv]

	lines_send = [x for x in lines if x.find("->") >= 0]
	lines_send = [x.split(" ") for x in lines_send]
	lines_send = [{"time": int(x[0]), "node": x[1], "tag": x[4], "s": "send"} for x in lines_send]

	# make pairs of send-receive ops
	lines_net = []
	for x in lines_send:
		lines_net.append(x)

	for x in lines_recv:
		lines_net.append(x)

	def skey(o):
		return o["time"]

	# sort events by time
	lines_net = sorted(lines_net, key=skey)
	lines_net_paired = []
	while(len(lines_net) > 0):
		# get first send
		send = None
		for x in lines_net:
			if x["s"] == "send" and send == None:
				send = x
				lines_net.remove(x)
				break

		# find pair
		recv = None
		for x in lines_net:
			if x["s"] == "recv" and recv == None and x["tag"] == send["tag"]:
				recv = x
				lines_net.remove(x)
				break

		lines_net_paired.append({
			"time_s" : send["time"],
			"time_e" : recv["time"],
			"node_s" : send["node"],
			"node_e" : recv["node"],
			"tag" : recv["tag"]
		})

	# split task scheduling in bins
	bins = {
		"0-0" : [],
		"0-1" : [],
		"1-1" : [],
		"1-0" : []
	}

	# add scheduling to bins (also add unique elem-names)
	elem_names_counter = 0
	for x in lines_sched:
		bins[x["node"]].append({
			"time": x["time"],
			"node": x["node"],
			"task": x["task"],
			"elem": "e_" + str(elem_names_counter)
		})
		elem_names_counter = elem_names_counter + 1
	
	# tag source and destination elems in messages
	for x in lines_net_paired:
	
		# find sender	
		min_dist_e = None
		for e in bins[x["node_s"]]:
			if(min_dist_e is None): # and e["task"] != "IDLE"):
				min_dist_e = e
				print(e)
			else:
				if e["time"] <= x["time_s"]: # and e["task"] != "IDLE":
					min_dist_e = e
				else:
					break

		x["elem_s"] = min_dist_e["elem"]

		# find receiver
		min_dist_e = None
		for e in bins[x["node_e"]]:
			if(min_dist_e is None): # and e["task"] != "IDLE"):
				min_dist_e = e
			else:
				if e["time"] > x["time_e"]: # and e["task"] != "IDLE":
					min_dist_e = e
					break

		x["elem_e"] = min_dist_e["elem"]


	lines = []

	# update task endtime
	for k in bins.keys():
		for e in bins[k]:

			# find next task
			next = None
			for f in bins[k]:	
				if(f["time"] > e["time"]):
					next = f
					break

			# udpate endtime
			if next is not None:
				e["time_e"] = next["time"] - KERNEL_SCHED_TIME
			else:
				e["time_e"] = e["time"] + KERNEL_SCHED_TIME


	# find max time and adjust scale
	tmax = 0
	for k in bins.keys():
		for m in bins[k]:
			if(m["time_e"] > tmax):
				tmax = m["time_e"]

	scale = int(tmax / 100)
	
	# ;;;
	for k in bins.keys():
		current_time = 0
		lines.append("\\ganttgroup[inline=false,group/.style={draw=none, fill=none}]{PE " + k + "}{0}{50}")
		for e in bins[k]:
			if(e["task"] != "IDLE"):
				lines.append("\\ganttbar[name=" + e["elem"] + "]{" + e["task"] + "}{" + str(int(e["time"] / scale)) + "}{" + str(int(e["time_e"] / scale) -1) + "}")
			else:
				lines.append("\\ganttbar[bar/.append style={fill=gray}, name=" + e["elem"] + "]{}{" + str(int(e["time"] / scale)) + "}{" + str(int(e["time_e"] / scale) -1) + "}")

		lines.append("\\\\")

	for l in lines:
		print(l)

	for x in lines_net_paired:
		print("\\ganttlink[link type=s-s]{" + x["elem_s"] + "}{" + x["elem_e"] + "}")

	print(f"1t.u. = {scale} cycles")

			
		



if __name__ == "__main__":
	main(argv[1::])
