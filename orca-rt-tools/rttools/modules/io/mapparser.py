from rttools.terminal.terminal import error, info, warn
from os.path import exists as file_exists
import sys

import networkx as nx

NEWLINE = '\n'

sys.path.append('../lib')

def loadFromFile(map_file):

  if not file_exists(map_file):
    error('Unable to load mapping file. Could not locate file "' + map_file + '".')
    exit(1)
  else: 
    return parseMap(map_file)

# parses a list of entries from the given mapping file
def parseMap(sourceFile):

  with open(sourceFile) as f:
    lines = f.read().splitlines() 

  entries = []
  
  for line in lines:
    split = line.split(':')
    entries.append({"node" : split[0], "tasks" : split[1].split(',')})

  return entries

