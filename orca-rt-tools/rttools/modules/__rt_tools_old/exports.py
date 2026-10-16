import networkx as nx
import sys
import os.path
from os import path
import pygraphviz
import random

# Importing the matplotlib.pyplot
import matplotlib.pyplot as plt

def formatSchedData(packets):

  # enumerate links
  links = {}

  for p in packets:
    for l in p['path']:
      label = l['data']['label']
      vec = []

      if label in links:
        vec = links[label]

      vec.append({ 
        'name': p['name'],
        'release': p['release'], 
        'net_time': p['net_time']}
      )
            
      links[label] = vec
  return links

def printSched(packets, hp):

  YTICKSFACTOR = 1

  links = formatSchedData(packets)

  fig, ax = plt.subplots()

  # for each links, add a ticks to the y-axis 
  # each 5 units
  yticks = []
  yticks_labels = []
  yticks_counter = YTICKSFACTOR
  for l in links:
    yticks.append(yticks_counter)
    yticks_counter = yticks_counter + YTICKSFACTOR
    yticks_labels.append(l)

    # print link rectangles
    vec = links[l]
    for v in vec:
      #add blue rectangle
      ax.broken_barh(
        [(v['release'], v['net_time'])],
        (yticks_counter - YTICKSFACTOR * 1.3, YTICKSFACTOR / 2),
        alpha=0.5
      )
      # ax.annotate(v['name'], (int(v['release']), int(v['net_time'])),
      #   xytext=(0.8, 0.9), textcoords='axes fraction',
      #   arrowprops=dict(facecolor='black', shrink=0.05),
      #   fontsize=16,
      #   horizontalalignment='right', verticalalignment='top'
      # )
      ax.annotate(v['name'], xy=[v['release'], v['net_time']], xycoords='figure points')

  # limit the range of the axis 
  ax.set_ylim(0, yticks_counter)

  # set the ticks and their labels
  ax.set_yticks(yticks, labels=yticks_labels)

  ax.set_xlim(0, hp)
  ax.set_xlabel('discrete time domain (cycles)')

  ax.grid(False)
  # ax.annotate('race interrupted', (61, 25),
  #             xytext=(0.8, 0.9), textcoords='axes fraction',
  #             arrowprops=dict(facecolor='black', shrink=0.05),
  #             fontsize=16,
  #             horizontalalignment='right', verticalalignment='top')

  plt.show()


# Exports a graph to a png file. By design, dot generates
# plot layout (requires graphviz)
def exportGraphImage(infile, outfile):
  if not path.exists(infile):
    print("unable to read input file")
    exit(0)

  graph = nx.read_gml(infile)
  gvizGraph = nx.nx_agraph.to_agraph(graph)
  gvizGraph.layout(prog = "dot") #defaults to neato if ommited
  gvizGraph.draw(outfile)

