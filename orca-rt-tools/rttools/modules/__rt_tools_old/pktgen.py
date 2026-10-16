from asyncio import subprocess
import networkx as nx
import json
from os import path
import os.path
from mapping import parseMap
from mapping import getMap
from routing import XY
from routing import getNumFlits
from routing import manhattan
from routing import getRoutingTime
from lcm import lcm
from terminal import info, wsfill, error, debug
from exports import printSched, exportGraphImage
from parseznc import parseznc, parseoccup
from vhdl import generateVhdlSimInput
import subprocess

DEBUG = True
ZINC_APP   = 'minizinc'
#ZINC_MODEL  = '../minizinc/CM/CM-v20211013.mzn'
ZINC_MODEL  = '../minizinc/CM/CM-v20220427.mzn'
#ZINC_MODEL  = '../minizinc/CM/CM-v20220518.mzn'
ZINC_SOLVER = 'Gecode'
ZINC_INPUT_PAD = 7
ZINC_THREADS = 4
OCCUPANCY_TEMPLATE_PLACEHOLDER = 'X'

# extract flows from a given application graph edges
# returns a list of flows
def extractFlows(edges):
  flows = []
  for e in edges:
    source, target, data = e

    flow = ({
      "name" : data["label"],  # name of the flow, must be unique among the flows
      "source" : source,       # task that generates the flow (task id)
      "target" : target,       # task that will receive the packets (task id)  
      "period" : data["period"],       # packets injection period
      "datasize" : data["datasize"],   # number of bytes to send
      "deadline" : data["deadline"] }) # deadline
    flows.append(flow)

  # sort flows by label (usually f1, f2, ...)
  flows.sort(key=lambda x : x["name"], reverse=False)

  return flows

# checks whether a vector constains only "-1" values
def nulline(i):
  res = True
  for j in i:
    if j != -1:
      res = False
      break
  return res

# generates packets for a given list of flows. packets 
# are generated for the whole hyperperiod hp
def getPacketsFromFlows(flows, hp):
  packets = []
  for f in flows:

    min_start = 0 
    period = 0
    i = 0
    while min_start < hp:
      packet = ({"name" : f["name"] + ":" + str(i), "flow" : f["name"], 
        "source" : f["source"], "target" : f["target"],
        "min_start" : min_start, "abs_deadline" : min_start + f["deadline"],
        "datasize" : f["datasize"]})
      packets.append(packet)
      min_start = min_start + f["period"]
      i = i + 1

  return packets

# returns a matrix whose dimensions are equals to the given matrix
def mcopy(matin):
  m = []
  for i in matin:
    n = []
    for j in i:
      n.append(j)
    m.append(n)
  return m

def vcopy(vecin):
  newvec = []
  for i in vecin:
    newvec.append(i)
  return newvec

def genTable(label, table, header = ""):
  
  lines = []
  lines.append(header)
  lines.append(label + " = ")
  
  c = 0
  first_line = True
  for i in table:
    if not nulline(i): ##prints only if non-empty
      if not first_line:
        line = " "
      else:
        line = "["
      line = line + "| "

      for j in table[i]:
        line = line + wsfill(j, 5) + ",   "
      
      line = line + "%" + i

      lines.append(line)
      first_line = False
    c = c + 1
  lines.append("|];")

  return '\n'.join(lines, )

# generate a list of packets from models
def pktGen(appfile, mapfile, archfile):

  if not path.exists(appfile):
    error("Could not read application file")
    exit()

  if not path.exists(mapfile):
    error("Could not read mapping file")
    exit()

  if not path.exists(archfile):
    error("Could not read architecture file")
    exit()

  info("Reading `" + appfile + "`")
  app = nx.read_gml(appfile)   # read application model
  info("Reading `" + archfile + "`")
  arch = nx.read_gml(archfile) # read topology file (architecture)
  info("Reading `" + mapfile + "`")
  mapping = parseMap(mapfile)  # read mapping file (node-to-tasks)
  

  info("Exporting PNG file for `" + appfile + "`")
  appname = (appfile.split('/')[-1].split('.')[0])
  exportGraphImage(appfile, "../applications/" + appname + ".png")

  # locate flows within application
  flows = extractFlows(app.edges(data=True))
  
  if DEBUG == True:
    for f in flows:
      debug(str(f))

  # calculate hyperperiod
  periods = []
  for f in flows:
    periods.append(f["period"])

  hp = lcm(periods)
  info("Hyperperiod for the entered flow set is " + str(hp))

  # get packets from flows
  packets = getPacketsFromFlows(flows, hp)
  info("Extracted " + str(len(packets)) + " packets from " + str(len(flows)) + " flows")

  if DEBUG == True:
    for p in packets:
      debug(str(p))

  info("Discovering packets routes...")

  # get traversal path of each packet
  for p in packets:
    sourceTaskName = ""
    targetTaskName = ""

    for n in app.nodes(data=True):
      id, data = n
      if id == p["source"]:
        sourceTaskName = id
      if id == p["target"]:
        targetTaskName = id

    sourceNode = getMap(sourceTaskName, mapping)
    targetNode = getMap(targetTaskName, mapping)

    ppath = XY(sourceNode, targetNode, arch)

    p['path'] = ppath

    if DEBUG == True:
      debug(p['name'] + ": hops=" + str(len(ppath)))
      for p in ppath:
        debug("    " + str(p))

  info("Enumerating network links...")

  # enumerate network links
  nlinks = []
  for e in arch.edges(data=True):
    nlinks.append(e)

  # add local-to/from links 
  for n in arch.nodes(data=True):
    x, y = n
    nlinks.append((x, 'L', {'label': str(x) + '-L'}))
    nlinks.append(('L', x, {'label': 'L-' + str(x)}))

  if DEBUG == True:
    for n in nlinks:
      debug(str(n))

  info("... Discovered " + str(len(nlinks)) + " links")


  # calculate net_time
  info("Calculating networking time...")
  
  for p in packets:
    sourceTaskName = ""
    targetTaskName = ""

    for n in app.nodes(data=True):
      id, data = n
      if id == p["source"]:
        sourceTaskName = id
      if id == p["target"]:
        targetTaskName = id

    source = getMap(sourceTaskName, mapping)
    target = getMap(targetTaskName, mapping)

    delta_m = manhattan(source, target, arch)
    routing_time = (delta_m + 1) * getRoutingTime()
    payload = getNumFlits(int(p["datasize"]))
    p['net_time'] = payload + routing_time + 1

    if DEBUG == True:
      debug(p['name'] + "=" + str(p['net_time']) +
        " dm=" + str(delta_m) +
        " ffrt=" + str(routing_time) +
        " payload=" + str(payload))

  # Generate template matrix, represents the relation P x R, where 
  # P is the set of all packets and R is the set of all resources. 
  # Resources are represented by links, thus the len(nlinks).
  occupancy_line = [-1 for j in range(len(packets))]
  occupancy = {}
  min_start = {}
  deadline  = {}

  for l in nlinks:
    s, t, o = l
    occupancy[o['label']] = vcopy(occupancy_line)
    min_start[o['label']] = vcopy(occupancy_line)
    deadline[o['label']] = vcopy(occupancy_line)
  
  # fill occupancy template
  for i in range(0, len(packets)):
    paths = packets[i]['path']
    for p in paths:
      l = p['data']['label']

      # update deadline
      link = deadline[l]
      link[i] = packets[i]['abs_deadline']
      deadline[l] = link

      # update min_start
      link = min_start[l]
      link[i] = packets[i]['min_start']
      min_start[l] = link

      # update occupancy
      link = occupancy[l]
      link[i] = packets[i]['net_time']
      occupancy[l] = link

  # find unused links
  to_remove = []
  for f in occupancy:
    l = occupancy[f]
    has = False
    for ll in l:
      if ll != -1 :
        has = True
        break
    if has != True:
      to_remove.append(f)

  for i in to_remove:
    del occupancy[i]
    del min_start[i]
    del deadline[i]

  info('Cleaned up ' + str(len(to_remove)) + ' unused network links')

  if DEBUG == True:
    debug("occupancy")
    for i in occupancy:
      debug(i + ' ' + str(occupancy[i]))
    debug("min_start")
    for i in min_start:
      debug(i + ' ' + str(min_start[i]))
    debug("deadline")
    for i in deadline:
      debug(i + ' ' + str(deadline[i]))
  
  # generate header 
  header = "% "
  for p in packets:
    header = header + p["name"] + " "


  info("Generating optimization problem (Minizinc export)...")

  # generate minizinc tables  
  info("... problem size: " + str(len(packets)) + "-by-" + str(len(occupancy)))

  tOccupancy = genTable("occupancy", occupancy, header)
  tDeadline = genTable("deadline", deadline, header)
  tMinStart = genTable("min_start", min_start, header)

  if DEBUG == True:
    debug(str(tOccupancy))
    debug(str(tDeadline))
    debug(str(tMinStart))

  linkNames = "% [ " + "\", \"".join(list(occupancy.keys())) + "]"

  lines = []
  lines.append(linkNames)
  lines.append("hp = " +  str(hp) + ";")
  lines.append("num_links = " + str(len(occupancy)) + ";")
  lines.append("num_packets = " + str(len(packets)) + ";")
  lines.append("")
  lines.append(tOccupancy)
  lines.append("")
  lines.append(tDeadline)
  lines.append("")
  lines.append(tMinStart)

  # write minizinc input to disk
  mzFile = '../minizinc/' + appname + '.dzn'
  info("Writing to `" + mzFile + "`")
  with open(mzFile, 'w+') as file:
    for l in lines:
      file.write(l + '\n')

  info("Checking for Minizinc installation...")
  try:
    sp = subprocess.run([ZINC_APP, '--version'], stdout=subprocess.PIPE)
    version = sp.stdout.decode('utf-8').split("\n")
    for l in version:
      if len(l) > 0:
        info("... " + l)
  except:
    error("Unable to locate Minizinc installation in this system, aborting")
    exit()

  info("Invoking Minizinc with...")
  cmd = [ZINC_APP, "--solver", ZINC_SOLVER, ZINC_MODEL, mzFile, "-p", str(ZINC_THREADS)]
  info("... `" + " ".join(cmd) + "`")
  info("Waiting for " + ZINC_APP + " to finish processing, please wait (it may take a while)")
  sp = subprocess.run(cmd, stdout=subprocess.PIPE)  

  zincres = sp.stdout.decode('utf-8')

  #TODO: fix print
  if(DEBUG):
    debug(zincres)

  # leaves if unsatisfiable
  if zincres.startswith("====="):
    info("... `" + zincres.replace('\n','') + "`")
    info("... problem is unsatisfiable, could not acquire injection time table!")
    info("All done.")
    exit()
  else: 
    info("... solution found!")

  voccupancy = parseoccup(occupancy)
  releases = parseznc(zincres)
  
  info("Collecting schedule from minizinc output...")
  #final packets characterization, scheduled
  schedule = []
  for i in range(0, len(packets)):
    p = packets[i]
    r = releases[i]
    o = voccupancy[i]
    schedule.append({
      'name' : p['name'],
      'flow' : p['flow'],
      'source' : {
        'task' : p['source'],
        'node' : getMap(p['source'], mapping)
      },
      'target' : {
        'task' : p['target'],
        'node' : getMap(p['target'], mapping)
      },
      'min_start' : p['min_start'],
      'abs_deadline' : p['abs_deadline'],
      'datasize_bytes' : p['datasize'],
      'num_flit' : getNumFlits(p['datasize']),
      'release' : r,
      'net_time' : o,
      'path' : p['path']
    })   

  # gen vhdl sim files
  location = os.path.dirname(os.path.realpath(__file__)) + "/../pkt-sim/packets/"
  info("Generating pkt-sim input at `" + location + "`")
  sources = generateVhdlSimInput(arch, schedule, location)
  
  if(DEBUG):
    debug(sources)

  # plot
  info("Plotting using `matplotlib`...")
  printSched(schedule, hp)