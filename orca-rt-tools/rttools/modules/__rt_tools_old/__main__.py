from heapq import merge
import networkx as nx
import sys
import os.path
import merge
from merge import merge
from os import path

from rttool import rttool
def main():
  # programa requires at least one command 
  if len(sys.argv) != 4:
    print("usage:")
    print("  python3 " + sys.argv[0] + " <app.gml> <mapping.map> <noc.gml>")
    exit(0)

  rttool(sys.argv[1], sys.argv[2], sys.argv[3])  

# Automatically jumps to main if called from command line
if __name__ == "__main__":
  main()
