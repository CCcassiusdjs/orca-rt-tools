import sys
import os.path
from os import path

# Extracts one line from the parsed CSV matrix 
# while removing whitespaces, linebreaks and tabs
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

  if len(charBuffer) > 0:
    item = int(''.join(charBuffer))
    items.append(item) #prevent last element from being skipped

  return items

# parse results from minizinc and scan 
# for the minimum release time among the
# the resources used by each packet. The
# result is a vector of `release_time`
def parseznc(input):

  firstLine = True
  max = []

  lines = input.split('\n')
  for line in lines:

    if not line.startswith("--") and len(line) > 1:
      row = formatLine(line)
      
      if firstLine:
        max = row
        firstLine = False
      else:    
        for i in range(0, len(row)):
          if row[i] != -1:
            if max[i] == -1 or max[i] > row[i]:
              max[i] = row[i]

  return max


# get network time from max occupancy
def parseoccup(occupancy):

  firstLine = True

  max = []

  for f in occupancy:
    row = occupancy[f]

    if firstLine:
      max = row
      firstLine = False
    else:    
      for i in range(0, len(row)):
        if row[i] > max[i]:
          max[i] = row[i]
  return max