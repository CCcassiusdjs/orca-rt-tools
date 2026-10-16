
hyperperiod = 55

packets = ["p1", "p2", "p3", "p4", "p5"]

links = [ "0-1", "1-3", "2-3", "2-0", "3-1", "3-2", "0-L", "L-0", "1-L", "L-2", "3-L", "L-3"]

occupancy = [
  #  p1    p2    p3    p4  p5
  [  18,   32, None, None, None],   # 0-1
  [None,   32, None, None, None],   # 1-3
  [None, None,   19,   27, None],   # 2-3
  [None, None, None, None,   23],   # 2-0
  [None, None, None,   27, None],   # 3-1
  [None, None, None, None,   23],   # 3-2
  [None, None, None, None,   23],   # 0-L
  [  18,   32, None, None, None],   # L-0
  [  18, None, None,   27, None],   # 1-L
  [None, None,   19,   27, None],   # L-2
  [None,   32,   19, None, None],   # 3-L
  [None, None, None, None,   23]    # L-3
]

deadline = [
  #  p1    p2    p3    p4  p5
  [  55,   55, None, None, None],   # 0-1
  [None,   55, None, None, None],   # 1-3
  [None, None,   55,   55, None],   # 2-3
  [None, None, None, None,   55],   # 2-0
  [None, None, None,   55, None],   # 3-1
  [None, None, None, None,   55],   # 3-2
  [None, None, None, None,   55],   # 0-L
  [  55,   55, None, None, None],   # L-0
  [  55, None, None,   55, None],   # 1-L
  [None, None,   55,   55, None],   # L-2
  [None,   55,   55, None, None],   # 3-L
  [None, None, None, None,   55]    # L-3
]

min_start = [
  #  p1    p2    p3    p4  p5
  [   0,    0, None, None, None],   # 0-1
  [None,    0, None, None, None],   # 1-3
  [None, None,    0,    0, None],   # 2-3
  [None, None, None, None,    0],   # 2-0
  [None, None, None,    0, None],   # 3-1
  [None, None, None, None,    0],   # 3-2
  [None, None, None, None,    0],   # 0-L
  [   0,    0, None, None, None],   # L-0
  [   0, None, None,    0, None],   # 1-L
  [None, None,    0,    0, None],   # L-2
  [None,    0,    0, None, None],   # 3-L
  [None, None, None, None,    0]    # L-3
]

problem = {
  'min_start' : min_start,
  'occupancy' : occupancy,
  'deadline' : deadline,
  'packets' : packets,
  'links': links,
  'hyperperiod' : hyperperiod
}