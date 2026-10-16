from email.quoprimime import quote
import sys
import os.path
from os import path
import csv

NEWLINE = '\n'

def getTaskIdByName(name, list):
  for i in list:
    if i["label"] == name:
      return i["id"]

def parseTaskRow(par):
  return {
    "id" : par[0],
    "label" : par[1],
    "period" : par[2],
    "capacity" : par[3],
    "deadline" : par[4],
    "description" : par[5]
  }

def parseFlowRow(par):
  return {
    "id" : par[0],
    "source" : par[1],
    "target" : par[2],
    "period" : par[3],
    "capacity" : par[4],
    "deadline" : par[5]
  }

def exportGmlTasks(tasks):
  gmlTasks = []
  for t in tasks:
    gmlTasks.append(
      "  node [" + NEWLINE + 
      "    id " + t["id"] + NEWLINE + 
      "    label \""  + t["label"] + "\"" + NEWLINE + 
      "    alias \""  + t["description"] + "\"" + NEWLINE + 
      "    period "   + t["period"].replace(',', '') + NEWLINE + 
      "    capacity " + t["capacity"].replace(',', '') + NEWLINE + 
      "    deadline " + t["deadline"].replace(',', '') + NEWLINE + 
      "  ]"
    )
  return gmlTasks

def exportGmlFlows(tasks, flows):
  gmlFlows = []
  for f in flows:
    gmlFlows.append(
      "  edge [" + NEWLINE +
      "    source " + getTaskIdByName(f["source"], tasks) + NEWLINE +
      "    target " + getTaskIdByName(f["target"], tasks) + NEWLINE +
      "    label f" + str(len(gmlFlows) +1) + NEWLINE + 
      "    period "   + f["period"].replace(',', '') + NEWLINE +
      "    datasize " + f["capacity"].replace(',', '') + NEWLINE +
      "    deadline " + f["deadline"].replace(',', '') + NEWLINE +
      "  ]"
    )
  return gmlFlows

# Exports a graph to a png file. By design, dot generates
# plot layout (requires graphviz)
def csv2app(infile, outfile):
  
  if not path.exists(infile):
    print("unable to read input file")
    exit(0)

  tasks = []   # store parsed tasks 
  flows = []   # store parsed flows

  # mode state machine
  # 0: seeking #tasks header 
  # 1: ignoring fields header
  # 2: parsing tasks, seeks #flows header
  # 3: ignoring fields header
  # 4: parsing flows
  mode = 0

  with open(infile) as csvfile:
    rows = csv.reader(csvfile)
    for row in rows:
      # seeks #tasks header, keep ignoring lines until it
      # finds the header 
      if mode == 0 :
        if(row[0].startswith("#tasks")):
          mode = 1
      # ignore fields header line
      elif mode == 1:
        mode = 2
      # parse line as a task 
      elif mode == 2:
        if(row[0].startswith("#flows")):
          mode = 3
        else:
          tasks.append(parseTaskRow(row))
      # ignoring fields header line
      elif mode == 3:
        mode = 4
      # parse line as a flow
      elif mode == 4:
        flows.append(parseFlowRow(row))

  gmlTasks = exportGmlTasks(tasks)
  gmlFlows = exportGmlFlows(tasks, flows)

  gmlFile = []
  gmlFile.append("graph ["  + NEWLINE)
  gmlFile.append("  directed 1" + NEWLINE)

  for t in gmlTasks:
    gmlFile.append(t + NEWLINE)

  for f in gmlFlows:
    gmlFile.append(f + NEWLINE)

  gmlFile.append("]")

  with open(outfile, "w+") as file:
    for i in gmlFile:
      file.write(i)


from rttool import rttool
def main():
  # programa requires at least one command 
  if len(sys.argv) != 3:
    print("usage:")
    print("  python3 " + sys.argv[0] + " <csv> <outfile>")
    exit(0)

  csv2app(sys.argv[1], sys.argv[2])

# Automatically jumps to main if called from command line
if __name__ == "__main__":
  main()
