from terminal import error 

def bandwidthSum(min_start, occupancy, deadline, packets, links, hyperperiod):
  # find the sum of capacity for all links
  sums = [0 for x in occupancy]
  
  for l in range(0, len(occupancy)):
    for p in range(0, len(occupancy[0])):
      if(occupancy[l][p] != None):
        sums[l] += occupancy[l][p]

  for s in sums:
    if(s > hyperperiod):
        error("Prelaunch test failed due to link capacity overflow!")
        print(sums)
        exit(1)
    
def prelaunchtest(problem):
  # tests whether all links has enough bandwidth to 
  # support all allocated traffic
  return bandwidthSum(
    problem['min_start'], 
    problem['occupancy'], 
    problem['deadline'],
    problem['packets'],
    problem['links'],
    problem['hyperperiod']
  )