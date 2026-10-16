
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