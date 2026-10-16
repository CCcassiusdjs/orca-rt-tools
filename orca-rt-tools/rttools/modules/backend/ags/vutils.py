
'''
Prints a matrix, row by row.
'''
def mprint(m):
  for i in m:
    print(i)

'''
Copies given vector and returns a new 
vector containing the same elements as 
the entered vector.
@param m the input vector
@returns a vector containing the same elements of m
'''
def vcopy(m):
  v = []
  for i in m:
    v.append(i) 
  return v   

'''
Copies a bi-dimensional matrix and returns a 
new matrix containing the same elements as the 
entered matrix.
@param m the input matrix
@returns a matrix containing the same elements of m
'''
def mcopy(m):
  v = []
  for i in m:
    v.append(vcopy(i))
  return v