from rttools.terminal.terminal import error, info, warn
from os.path import exists as file_exists
import sys

import networkx as nx

NEWLINE = '\n'

sys.path.append('../lib')

def loadFromFile(noc_gml):

  if not file_exists(noc_gml):
    error('Unable to load NoC topology file. Could not locate file "' + noc_gml + '".')
    exit(1)
  else: 
    return parseNoc(noc_gml)


def parseNoc(noc_gml):
  return nx.read_gml(noc_gml)
