import json
from terminal import colors, wsfill

DEBUG = False

# 
def formatLine(line):
  charBuffer = []
  items = []

  for c in line:
    if(c == ' ' or c == '\t' or c == '\n'):
      if len(charBuffer) > 0:
        item = int(''.join(charBuffer))
        items.append(item)
        charBuffer = []
    else:
      charBuffer.append(c)

  return items

# parse data from minizinc result log
def znc2csv (infile):

  firstLine = True
  rows = []

  with open(infile) as f:

    for line in f:
      if firstLine:
        rows = formatLine(line)
        firstLine = False
      else:
        column = formatLine(line)
        for i in range(0, len(column)):
          if column[i] != -1:
            if rows[i] == -1 or rows[i] > column[i]:
              rows[i] = column[i]
    
  return rows

def merge(pkts, znc):
  packets = []
  release = None

  # loads packets from previously exported file
  with open(pkts, 'r') as fpkt:
    lines = fpkt.readlines()
    for l in lines:
      packets.append(json.loads(l))

  # loads data from minizinc results 
  release = znc2csv(znc)

  # CHECK - compare size of lists; there must be
  # one release time per packet
  if(len(packets) != len(release)):
    print(colors.WARN + "warning: Number of release times mismatch the number of packets." + colors.END)
  
  # append release time to packet structures
  i = 0
  padding = len(str(max(release)))

  for i in range(0, len(packets)):
    p = packets[i]
    r = release[i]
    print(colors.BLUE, wsfill(r, padding), colors.WARN, p, colors.END)


