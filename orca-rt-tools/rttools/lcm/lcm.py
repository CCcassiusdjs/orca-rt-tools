#least common multiplier
def lcm(integers):

  tmpsum = []
  [tmpsum.append(x) for x in integers if x not in tmpsum]

  # !TODO array copy
  initial = []
  for i in tmpsum:
    initial.append(i)

  itcount = 0

  while True:

    itcount = itcount + 1
        
    if itcount > 1000:
      return 0
    
    # 1195312, 95625, 239062, 2390625

    # check whether all numbers are the same
    last = tmpsum[0]
    done = True
    for i in tmpsum:
      if i != last:
        done = False
        break

    # abandon algorithm if all elements are equals
    if done:
      #print('returned', tmpsum[0])
      #print(str(integers))
      #print(tmpsum)
      #print(initial)
      return tmpsum[0]

    # scan for the least value in the list 
    least = 0
    for i in range(0, len(tmpsum)):
      if tmpsum[i] < tmpsum[least]:
        least = i

    # increment it by the initial value
    tmpsum[least] = tmpsum[least] + initial[least]