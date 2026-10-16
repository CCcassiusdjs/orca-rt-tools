from rttools.modules.backend.ags import search3
from rttools.modules.backend.ags import heuristics

from rttools.terminal.terminal import warn, error, info

# lstf(solution_space),  packet with the least slack time first
# mcpf(occupancy),       packet in most conflicting links first
# mbuf(occupancy),       packets with most network overhead first
HEURISTIC = heuristics.lstf
STEP = 100
TRIES = 500

def agsExport(packets, links, hp, mapping, arch, appname, prunning, fail, heuristic):

  min_start = [[None for y in range(0,len(packets))] for x in range(0, len(links))]
  occupancy = [[None for y in range(0,len(packets))] for x in range(0, len(links))]
  deadline = [[None for y in range(0,len(packets))] for x in range(0, len(links))]

  for l in range(0, len(links)):
    source, target, data = links[l]
    label = data['label']

    for p in range(0, len(packets)):
      paths = packets[p]['path']
      # links of the path and the extra resources of the packet (network
      # interfaces of its PEs, rttools/modules/routing/router.py)
      labels = [paths[e]['data']['label'] for e in range(0, len(paths))] + list(packets[p].get('resources', []))

      for label2 in labels:
        # packet has that link
        if(label == label2):
          min_start[l][p] = packets[p]['min_start']
          deadline[l][p] = packets[p]['abs_deadline']
          occupancy[l][p] = packets[p]['net_time']

  # remove unused links from tables
  removal = []
  for i in range(0, len(occupancy)):
    isNone = True
    for j in occupancy[i]:
      if j != None:
        isNone = False
        break
    if isNone:
      removal.append(i)
      
  # remove unused links from problem instance
  remIdx = 0
  for i in removal:
    del min_start[i - remIdx]
    del occupancy[i - remIdx]
    del deadline[i- remIdx]
    del links[i - remIdx] # <<
    remIdx = remIdx + 1


  problem = {
    'min_start' : min_start,
    'occupancy' : occupancy,
    'deadline' : deadline,
    'packets' : packets,
    'links': links,
    'hyperperiod' : hp
  }

  return problem, runAgs(problem, step=prunning, tries=fail, heuristic=heuristic)


def runAgs(problem, heuristic = HEURISTIC, step = STEP, tries = TRIES):
  info("This is Adaptive Guided Search. Parameters: step=" + str(step) + ", tries=" + str(tries))
  return search3.search3(problem, heuristic, tries, step)
  
  #saveSvg(res, problem, skipped)
