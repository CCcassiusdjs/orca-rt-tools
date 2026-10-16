#least common multiplier
def lcm(integers):

  # start de algorithm with current integer values
  tmpsum = [0] * len(integers)

  j = 0
  for i in integers:
    tmpsum[j] = i
    j = j + 1

  while True:
    # check whether all numbers are the same
    last = tmpsum[0]
    done = True
    for i in tmpsum:
      if i != last:
        done = False
        break;

    # abandon algorithm if all elements are equals
    if done:
      return tmpsum[0]

    # scan for the least value in the list 
    least = tmpsum[0]
    j = 0
    k = 0
    for i in tmpsum:
      if i < least:
        least = i
        k = j
      j = j + 1

    # increment it by the initial value
    tmpsum[k] = tmpsum[k] + integers[k]

def test_lcm():
  integers = [1,2,3,4,5]
  _lcm = lcm(integers)
  print(_lcm)

# Automatically jumps to main if called from command line
if __name__ == "__main__":
  test_lcm()

