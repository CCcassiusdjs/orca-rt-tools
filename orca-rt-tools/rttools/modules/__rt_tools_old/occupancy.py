import networkx as nx
import sys
import os.path
from os import path
import mapping
from mapping import parseMap
from mapping import getMap
import routing
from routing import XY
from routing import getNumFlits
from routing import manhattan
from routing import getRoutingTime

def generateHyperperiod(flows):
  return 78651
  # 1) collect all periods
  # 2) return math.lcm()

def mcopy(matin):
  m = []
  for i in matin:
    n = []
    for j in i:
      n.append(j)
    m.append(n)
  return m

# returns a list of paths from 
def generateOccupancy(appfile, mapfile, archfile):

  if not path.exists(appfile):
    print("unable to read application file")
    exit(0)

  if not path.exists(mapfile):
    print("unable to read mapping file")
    exit(0)

  if not path.exists(archfile):
    print("unable to read architecture file")
    exit(0)

  arch = nx.read_gml(archfile) # read topology file (architecture)
  mapping = parseMap(mapfile)  # read mapping file (node-to-tasks)
  app = nx.read_gml(appfile)   # read application model
  
  # locate flows within application
  flows = []
  for e in app.edges.items():
    edge, data = e
    flow = ({"name" : data["label"], "source" : edge[0], "target" : edge[1], 
      "period" : data["period"], "datasize" : data["datasize"], 
      "deadline" : data["deadline"] })
    flows.append(flow)

  # sort flows by lable (usually f1, f2, ...)
  flows.sort(key=lambda x : x["name"], reverse=False)

  # get mapping
  mapp = {}
  for f in flows:
    source = f["source"]
    mapp[source] = getMap(source, mapping)
    target = f["target"]
    mapp[target] = getMap(target, mapping)

  # for each flow, get paths 
  fpaths = []
  for f in flows:
    fpath = XY(mapp[f["source"]], mapp[f["target"]], arch)
    fpaths.append(fpath)

  # enumerate network links
  nlinks = []
  for e in arch.edges.items():
    nlinks.append(e)

  # generate occupancy matrix
  occupancy = [[0 for j in range(len(fpaths))] for i in range(len(nlinks))]

  ic = 0
  kc = 0
  OCCUPANCY_MARK = 'x'

  # fill occupancy for node-to-node links
  for i in fpaths:  
    for j in i:
      dj = j["data"]
      ik = 0
      for k in nlinks:
        ek, dk = k
        if dj["label"] == dk["label"]:
          occupancy[ik][ic] = OCCUPANCY_MARK
        ik += 1
    ic += 1

  # fill occupancy for node-to-pe and pe-to-node links
  i = len(nlinks)
  for node in arch.nodes.items():
    n, d = node
    nlinks.append([(n, 'L'), {'label': n + "-L"}])
    nlinks.append([('L', n), {'label': "L-" + n}])
    occupancy.append([0 for j in range(len(fpaths))])
    occupancy.append([0 for j in range(len(fpaths))])
    j = 0
    for f in flows:
      source = getMap(f["source"], mapping)
      if source == n:
        occupancy[i][j] = OCCUPANCY_MARK
      target = getMap(f["target"], mapping)
      if target == n:
        occupancy[i+1][j] = OCCUPANCY_MARK
      j += 1
    i += 2

  # generate occupancy matrices
  min_start = mcopy(occupancy)
  deadline = mcopy(occupancy)

  #fix sparse representation for all matrices
  i = 0
  for ii in min_start:
    j = 0
    for jj in ii:
      if occupancy[i][j] == 0:
        occupancy[i][j] = -1
        deadline[i][j] = -1
        min_start[i][j] = -1
      j += 1 
    i += 1

  # generate occupancy matrix
  # occupancy is (data_size / bus_width) + 1 + manhattan (source/target) 
  # manhattan is for mesh-only nets
  i = 0
  for l in nlinks:
    j = 0
    for f in flows:
      if occupancy[i][j] != -1:
        source = getMap(f["source"], mapping)
        target = getMap(f["target"], mapping)
        occupancy[i][j] = ((getNumFlits(f["datasize"]) -1) +
          manhattan(source, target, arch) * getRoutingTime()) 
      j += 1
    i += 1

  # generate deadline matrix (explicit in model)
  i = 0
  for l in nlinks:
    j = 0
    for f in flows:
      if deadline[i][j] != -1:
        deadline[i][j] = f["deadline"]
      j += 1
    i += 1

  # generate min_start matrix (deadline of source task)
  i = 0
  for l in nlinks:
    j = 0
    for f in flows:
      if min_start[i][j] != -1:
        sourceTask = None        
        for n in app.nodes.items():
          node, data = n
          if node == f["source"]:
            sourceTask = data
            break
        min_start[i][j] = sourceTask["deadline"]
      j += 1 
    i += 1

  #print("================== Mapping")
  #for entry in mapping:
  #  print(entry)

  #print("================== Flow paths")   
  #for f in flows:
  #  print(f)

  #print("================== Reverse Map")
  #print(mapp)

  #print("================== Flows")
  #for f in flows:
  #  print(f)

  #print("================== Network links")
  #for l in nlinks:
  #  print(l)

  # generate header 
  header = ""
  for f in flows:
    header = header + f["name"] + " "

  # variables
  print()
  hyperperiod = generateHyperperiod(flows)
  print("hyperperiod_length = ", hyperperiod, ";")
  print("num_links = ", len(nlinks), ";")
  print("num_packets = ", len(flows),  ";")
  print()

  print("% ", header)
  print("occupancy = [", end = '')
  c = 0
  for i in occupancy:
    print("| ", end = '')
    for j in i:
      print("%5d, " % j, end = '')
    print("  %", nlinks[c][1]["label"])
    c = c + 1
  print("|];")

  print()

  print("% ", header)
  print("min_start = [", end = '')
  c = 0
  for i in min_start:
    print("| ", end = '')
    for j in i:
      print("%5d, " % j, end = '')
    print("  %", nlinks[c][1]["label"])
    c = c + 1
  print("|];")

  print()

  print("% ", header)
  print("deadline = [", end = '')
  c = 0
  for i in deadline:
    print("| ", end = '')
    for j in i:
      print("%5d, " % j, end = '')
    print("  %", nlinks[c][1]["label"])
    c = c + 1
  print("|];")

  # vhdl 
  print()
  print("constant tp : tpacket := (")
  print("-- start  size  src  tgt  deadline ")
  i = 0
  for f in flows:
    print ("(", end = '')

    #locate source task, print WCET
    sourceTask = f["source"]
    sourceNode = getMap(sourceTask, mapping)

    for n in app.nodes.items():
      node, data = n
      if node == sourceTask:
        print(str(data["deadline"]) + ", ", end = '')
        break

    #print number of flits
    print(str(getNumFlits(f["datasize"])) + ", ", end = '')

    #locate source task, print node
    print(sourceNode + ", ", end = '')

    #locate target task, print node
    targetTask = f["target"]
    targetNode = getMap(targetTask, mapping)
    print(targetNode + ", ", end = '')

    #period
    print(f["period"], end = '')

    if i != len(flows) - 1:
      print("),", end = '')
    else:
      print(")", end = '')

    # packet alias
    print("    -- " + f["name"])
    i = i + 1
  print(");")

