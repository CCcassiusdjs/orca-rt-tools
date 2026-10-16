
hyperperiod = 78651

packets = ["p1", "p2", "p3", "p4", "p5", "p6", "p7"]

links = [ "0-1", "1-3", "2-4", "3-1", "3-2", "3-5", "4-5", "5-3", "L-0", "1-L", "L-1", "2-L", "L-2", "3-L", "L-3", "4-L", "L-4", "5-L", "L-5" ]



occupancy = [
#    p1       p2      p3       p4       p5       p6       p7
  [1043,    None,    None,    None,    None,    None,    None],   #0-1
  [1043,    None,    None,    None,    None,    None,    1043],   #1-3
  [None,    None,    1037,    None,    None,    None,    None],   #2-4
  [None,    None,    None,    None,    None,    1037,    None],   #3-1
  [None,    1037,    None,    None,    None,    None,    None],   #3-2
  [None,    None,    None,    None,    None,    None,    1043],   #3-5
  [None,    None,    None,      29,    None,    None,    None],   #4-5
  [None,    None,    None,    None,    2061,    None,    None],   #5-3
  [1043,    None,    None,    None,    None,    None,    None],   #L-0
  [None,    None,    None,    None,    None,    1037,    None],   #1-L
  [None,    None,    None,    None,    None,    None,    1043],   #L-1
  [None,    1037,    None,    None,    None,    None,    None],   #2-L
  [None,    None,    1037,    None,    None,    None,    None],   #L-2
  [1043,    None,    None,    None,    2061,    None,    None],   #3-L
  [None,    1037,    None,    None,    None,    1037,    None],   #L-3
  [None,    None,    1037,    None,    None,    None,    None],   #4-L
  [None,    None,    None,      29,    None,    None,    None],   #L-4
  [None,    None,    None,      29,    None,    None,    1043],   #5-L
  [None,    None,    None,    None,    2061,    None,    None]    #L-5
]

deadline = [ 
#    p1       p2       p3       p4       p5       p6       p7
  [36627,    None,    None,    None,    None,    None,    None],   #0-1
  [36627,    None,    None,    None,    None,    None,   70253],   #1-3
  [ None,    None,   53521,    None,    None,    None,    None],   #2-4
  [ None,    None,    None,    None,    None,   53521,    None],   #3-1
  [ None,   37346,    None,    None,    None,    None,    None],   #3-2
  [ None,    None,    None,    None,    None,    None,   70253],   #3-5
  [ None,    None,    None,   69632,    None,    None,    None],   #4-5
  [ None,    None,    None,    None,   78607,    None,    None],   #5-3
  [36627,    None,    None,    None,    None,    None,    None],   #L-0
  [ None,    None,    None,    None,    None,   53521,    None],   #1-L
  [ None,    None,    None,    None,    None,    None,   70253],   #L-1
  [ None,   37346,    None,    None,    None,    None,    None],   #2-L
  [ None,    None,   53521,    None,    None,    None,    None],   #L-2
  [36627,    None,    None,    None,   78607,    None,    None],   #3-L
  [ None,   37346,    None,    None,    None,   53521,    None],   #L-3
  [ None,    None,   53521,    None,    None,    None,    None],   #4-L
  [ None,    None,    None,   69632,    None,    None,    None],   #L-4
  [ None,    None,    None,   69632,    None,    None,   70253],   #5-L
  [ None,    None,    None,    None,   78607,    None,    None]    #L-5
]

min_start = [
  [    0,    None,    None,    None,    None,    None,    None],   #0-1
  [    0,    None,    None,    None,    None,    None,       0],   #1-3
  [ None,    None,       0,    None,    None,    None,    None],   #2-4
  [ None,    None,    None,    None,    None,       0,    None],   #3-1
  [ None,       0,    None,    None,    None,    None,    None],   #3-2
  [ None,    None,    None,    None,    None,    None,       0],   #3-5
  [ None,    None,    None,       0,    None,    None,    None],   #4-5
  [ None,    None,    None,    None,       0,    None,    None],   #5-3
  [    0,    None,    None,    None,    None,    None,    None],   #L-0
  [ None,    None,    None,    None,    None,       0,    None],   #1-L
  [ None,    None,    None,    None,    None,    None,       0],   #L-1
  [ None,       0,    None,    None,    None,    None,    None],   #2-L
  [ None,    None,       0,    None,    None,    None,    None],   #L-2
  [    0,    None,    None,    None,       0,    None,    None],   #3-L
  [ None,       0,    None,    None,    None,       0,    None],   #L-3
  [ None,    None,       0,    None,    None,    None,    None],   #4-L
  [ None,    None,    None,       0,    None,    None,    None],   #L-4
  [ None,    None,    None,       0,    None,    None,       0],   #5-L
  [ None,    None,    None,    None,       0,    None,    None]    #L-5
]
