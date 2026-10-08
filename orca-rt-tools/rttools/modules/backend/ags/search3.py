from rttools.modules.backend.ags.heuristics import resort
from rttools.terminal.terminal import debug, error, info, warn
from rttools.vector.vector import mcopy

'''
Checks whether two ranges overleap.
@param ra range a, the first range 
@param rb range b, the second range
@returns True if the ranger overleap, otherwise False

'''
def overleap(ra, rb):
  mina, maxa = ra
  minb, maxb = rb

  return not(maxa < minb or maxb < mina)

'''
Checks whether a given partial solution has a valid
solution within it. 
@param V the partial solution
@returns True if a solution is still feasible, False otherwise
'''
def check(V):
  for i in range(0, len(V)):
    for j in range(0, len(V[0]) - 1):
      if(V[i][j] != -1):
        rangea = V[i][j]
        for k in range(j + 1, len(V[0])):
          if(V[i][k] != -1):
            rangeb = V[i][k]
            if overleap(rangea, rangeb):
              return False
  return True

'''
Checks whether some packets conflits with
other packets in the model. 
'''
def check_consistency(V, O, idx, show=False):

  # acquire range for package at V[idx]
  rangea = (0,0)
  for i in range(0, len(V)):
    if(V[i][idx] != None):
      rangea = (V[i][idx], V[i][idx] + O[i][idx]) #first occurence!
      break

  # for each link in the model
  for l in range(0, len(V)):

    # ignore row if current packet doesnt use that link
    if(V[l][idx] != None):

      # for each packet in that link, find if it 
      # overleaps current packet
      for p in range(0, len(V[0])):
        if(p != idx and V[l][p] != None): # avoid comparing to itself
          rangeb = (V[l][p], V[l][p] + O[l][p])

          if(overleap(rangea, rangeb)):
            # if show:
            #   warn("conflict at link '" + str(l) + "'")
            return False
  return True

'''
Heuristic search. 
@param M minimum release time values 
@param O occupancy values
@param D deadline values 
@param V problem instance
@param h a heuristic vector 
'''

def hsearch(p, space, partial, h, depth, t, tries, step):

  # global counter for entered nodes
  hsearch.entered += 1

  # verify whether we reach a leaf node.
  # if node reached, then evaluate current
  # solution. If this is a suitable solution, 
  # return it. Otherwise keep going.
  if len(h) == 0:
    return partial

  # Select next node based on the heuristic. 
  # Ex. get the lesser slack time
  nnode = h.pop()

  # increment the number of time the algorithm entered this node
  t[nnode] += 1 #tries

  # print current solution node
  # used_links = []
  # for l in range(0, len(p['occupancy'])):
  #   if(p['occupancy'][l][nnode] != None):
  #     used_links.append(p['links'][l])

  # acquire packet solution range
  packet_range = (0,0) 
  for i in range(0, len(space)):
    if(space[i][nnode] != None):
      packet_range = space[i][nnode]
      break
  
  #debug("depth:" + str(depth) + "/" + str(len(p['packets'])) + " " + str(p['packets'][depth]))
  #  + " tries:" + str(t[nnode]) + "/" + str(tries)  + " | " + " ".join(used_links))

  # iterate through the range
  min, max = packet_range
  res = None

  # dvalue =  (max - min) / step
  # warn("Depth " + str(depth) + " reported ~" + str(int(dvalue)) + 
  #   " checkings. Visited " + str(t[nnode]) + " times.")

  # the window [min, max] is closed: max = deadline - occupancy is a valid
  # release (a packet with zero slack has min == max)
  for k in range(min, max + 1, step):

    # replace tentative starting time value for that package
    for i in range(0, len(space)):
      if(space[i][nnode] != None):
        partial[i][nnode] = k

    # Check consistency. If branch has a possible
    # solution, keep searching
    check = check_consistency(partial, p['occupancy'], nnode)

    if check:
      res = hsearch(p, space, partial, h, depth + 1, t, tries, step)
      if res != None:
        break
    else:
      hsearch.ignored += 1

  # rewrite values back to the partial solution before returning
  # replace value for that package
  if(res == None or res == "RESTART"):
    for i in range(0, len(space)):
      if(space[i][nnode] != None):
        partial[i][nnode] = None

  if(t[nnode] == tries):
    #return "RESTART"
    hsearch.skipped.append(nnode)
    error("Could not schedule " + str(p['packets'][nnode]['name']) + "! Restarting.")

    for l in range(0, len(p['occupancy'])):
      if (p['occupancy'][l][nnode] != None):
        debug(p['links'][l])

    check_consistency(partial, p['occupancy'], nnode, True)

    return None

  h.append(nnode)

  return res

'''
Self-counting!
'''
hsearch.entered = 0
hsearch.ignored = 0
hsearch.skipped = []

def search3(p, heuristic, tries, step):
  
  # Initial solution has no packets placed yet.
  # Rationally: select packet with the highest
  # value for the given heuristic. Place the 
  # selected packet and then select another one.
  partial_solution = [[None for x in p['occupancy'][0]] for y in p['occupancy']]

  # Generate ranges of solution here. At this 
  # point, we proceed as Minizinc, using intervalar
  # arithmetics. Sparse matrix notation takes '-1' as
  solution_space = mcopy(p['occupancy'])
  for i in range(0, len(solution_space)):
    for j in range(0, len(solution_space[i])):
      cell = solution_space[i][j]
      if(cell != None):
        solution_space[i][j] = (p['min_start'][i][j], p['deadline'][i][j] - p['occupancy'][i][j])

  # Heuristic
  h = heuristic(solution_space, p['min_start'], p['occupancy'], p['deadline'])

  t = [0 for x in p['occupancy'][0]] # packet tries counter

  res = "RESTART"
  skip = set()
  hsearch.entered = 0
  hsearch.ignored = 0
  hsearch.skipped = []
  while res == "RESTART":
    
    info("Fresh start, waiting for hsearch to finish")
    result = hsearch(p, solution_space, partial_solution, h, 0, t, tries, step)

    for i in hsearch.skipped:
      skip.add(i)
    
    if result == None:
      #print("No solution found.")
      return None

    if result != "RESTART":
      info("Solution found!")
      info("Ignored nodes: " + str(hsearch.ignored))
      info("Entered nodes: " + str(hsearch.entered))
      return (result, skip)

    for i in range(0, len(t)):
      if t[i] >= tries:
        t[i] += 1

    h = resort(t, p['packets'])

  # call search at node zero
  return (res, skip)
