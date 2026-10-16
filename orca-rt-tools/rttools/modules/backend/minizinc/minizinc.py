import subprocess
import traceback

from rttools.vector.vector import vcopy
from rttools.terminal.terminal import info, debug, error
from rttools.strgen.string import wsfill, genwss

from rttools.modules.io.znc import parseoccup, parseznc
from rttools.modules.io.svg2 import printSched
from rttools.modules.mapping.mapper import getMap
from rttools.modules.io.vhdl import generateVhdlSimInput
from rttools.modules.routing.router import getNumFlits

from os.path import dirname, realpath, join
from os import environ

# repository root: five levels above this file
# (minizinc -> backend -> modules -> rttools -> orca-rt-tools -> raiz)
_REPO_ROOT = realpath(join(dirname(realpath(__file__)), *([".."] * 5)))

ZINC_APP   = 'minizinc'
# ORT_ZINC_MODEL permite indicar outro modelo
ZINC_MODEL  = environ.get("ORT_ZINC_MODEL", join(_REPO_ROOT, "apps", "CM-v20220427.mzn"))
ZINC_SOLVER = 'Gecode'
ZINC_INPUT_PAD = 7
ZINC_THREADS = 4
OCCUPANCY_TEMPLATE_PLACEHOLDER = 'X'

# checks whether a vector constains only "-1" values
def nulline(i):
  res = True
  for j in i:
    if j != -1:
      res = False
      break
  return res

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

def minizincExport(packets, nlinks, hp, mapping, arch, appname):
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
  mzFile = './minizinc/' + appname + '.dzn'

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
    traceback.print_exc()
    error("Unable to locate Minizinc installation in this system, aborting")
    exit()

  info("Invoking Minizinc with...")
  cmd = [ZINC_APP, "--solver", ZINC_SOLVER, ZINC_MODEL, mzFile, "-p", str(ZINC_THREADS)]
  info("... `" + " ".join(cmd) + "`")
  info("Waiting for " + ZINC_APP + " to finish processing, please wait (it may take a while)")
  sp = subprocess.run(cmd, stdout=subprocess.PIPE)  

  zincres = sp.stdout.decode('utf-8')

  #TODO: format of the solver output
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
  sources = generateVhdlSimInput(arch, schedule)
  
  debug(sources)

  # plot
  info("Plotting using `matplotlib`...")
  printSched(schedule, hp)