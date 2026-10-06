import json
from sys import argv

KERNEL_SCHED_TIME = 200

# default map: application E (Ch. 8.3), PE "x-y" -> tasks by index;
# the key order defines the panel order
task_names = {
	"0-0": ['IDLE', 'F', 'D', 'B', 'A'],
	"0-1": ['IDLE', 'C'],
	"1-1": ['IDLE', 'J', 'G'],
	"1-0": ['IDLE', 'H', 'I', 'E']
}

# log time units per millisecond (old default: 10^6,
# that is, $time in ns)
DEFAULT_UNITS_PER_MS = 1000000
DEFAULT_OUTPUT = "gannt2.png"

colors = [
	'firebrick',
	'forestgreen',
	'chocolate',
	'deepskyblue',
	'mediumblue',
	'darkviolet',
]

# pkts = {
# 	1230 : {"source": "A", "target": "C"},
# 	4560 : {"source": "A", "target": "B"},
# 	7890 : {"source": "B", "target": "D"},
# 	1200 : {"source": "C", "target": "E"},
# 	3450 : {"source": "D", "target": "F"},
# 	6780 : {"source": "F", "target": "G"},
# 	9010 : {"source": "E", "target": "I"},
# 	2340 : {"source": "E", "target": "H"},
# 	5670 : {"source": "I", "target": "J"},
# 	8900 : {"source": "H", "target": "J"},
# 	1230 : {"source": "G", "target": "J"}
# }

# node address in the flit: (x << 8) | y
def f2na(flit_addr):
	addr = int(flit_addr, 16)
	x = (addr >> 8) & 0xFF
	y = addr & 0xFF
	return f"{x}-{y}"


def make_time_formatter(units_per_ms):
	return lambda x, pos: str(f"{x / units_per_ms} ms")


# converts the log lines into intervals per PE
def parse_log(lines, names):

	lines = [x.replace("\n","").replace("#", "").strip() for x in lines]
	lines = [x for x in lines if x.find("Elapsed") < 0]
	lines = [x for x in lines if x.find("workflow") < 0]
	lines = [x for x in lines if len(x) > 0]

	lines_sched = [x for x in lines if x.find("scheduled") >= 0]
	lines_sched = [x.split(" ") for x in lines_sched]
	lines_sched = [{"time": int(x[0]), "node": x[1], "task": names[x[1]][int(x[3])]}
		for x in lines_sched if x[1] in names]

	# split task scheduling in bins
	bins = {k: [] for k in names.keys()}

	# add scheduling to bins (also add unique elem-names)
	for x in lines_sched:
		bins[x["node"]].append({
			"time": x["time"],
			"node": x["node"],
			"task": x["task"],
			"time_e": x["time"]
		})

	# sort events in each bin
	for b in bins.keys():
		bins[b] = sorted(bins[b], key=lambda e: e["time"])

	# update events endtime
	for b in bins.keys():
		current_event = None
		for e in bins[b]:
			if current_event is not None:
				current_event["time_e"] = e["time"]
			current_event = e

	return bins


def parse_args(argv):
	opts = {"log": argv[0], "map": None, "out": DEFAULT_OUTPUT,
		"units_per_ms": DEFAULT_UNITS_PER_MS}
	i = 1
	while i < len(argv):
		if argv[i] == "--map":
			opts["map"] = argv[i + 1]
		elif argv[i] == "--out":
			opts["out"] = argv[i + 1]
		elif argv[i] == "--units-per-ms":
			opts["units_per_ms"] = float(argv[i + 1])
		else:
			raise ValueError("unknown option " + argv[i])
		i += 2
	return opts


def l2g_main(argv):

	opts = parse_args(argv)

	names = task_names
	if opts["map"] is not None:
		with open(opts["map"]) as f:
			names = json.load(f)

	with open(opts["log"]) as f:
		bins = parse_log(f.readlines(), names)

	import matplotlib
	matplotlib.use("Agg")
	import matplotlib.pyplot as plt

	# create master figure
	fig, gnt = plt.subplots(len(bins), 1, sharex=True, figsize=(12,8), squeeze=False)
	gnt = gnt[:, 0]
	fig.tight_layout(pad=1.0)
	plt.ticklabel_format(scilimits=(-99999999,99999999)) # prevents scientific notation
	plt.subplots_adjust(left=0.06, bottom=0.06, wspace=0.4, hspace=0.4)

	# locate min and max values (PEs without events are left out)
	vmin = None
	vmax = None

	for b in bins.keys():
		if len(bins[b]) == 0:
			continue
		min_time = bins[b][0]["time"]
		if(vmin == None or vmin > min_time):
			vmin = min_time

		max_time = bins[b][-1]["time_e"]
		if(vmax == None or vmax < max_time):
			vmax = max_time

	formatter = make_time_formatter(opts["units_per_ms"])

	k_idx = 0
	for k in bins.keys():

		# Y-axis config.
		gnt[k_idx].set_ylim(1, len(names[k]))
		gnt[k_idx].set_yticks(range(-1, len(names[k])))
		gnt[k_idx].set_yticklabels([" "] + names[k])
		gnt[k_idx].set_ylabel("Tasks, PE=" + k)

		# X-axis config.
		if vmin is not None and vmax is not None and vmax > vmin:
			gnt[k_idx].set_xlim(vmin, vmax)
		gnt[k_idx].set_xlabel("Time")
		gnt[k_idx].xaxis.set_major_formatter(formatter) # μ

		gnt[k_idx].grid(True)
		gnt[k_idx].set_axisbelow(True)

		for e in bins[k]:
			p_height = names[k].index(e["task"])
			gnt[k_idx].broken_barh([(e["time"], e["time_e"] - e["time"])], (p_height - 0.3, 0.6), facecolors =(colors[p_height % len(colors)]))

		k_idx = k_idx + 1

	plt.savefig(opts["out"], dpi=300)
