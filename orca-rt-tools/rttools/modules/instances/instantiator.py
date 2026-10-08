from rttools.terminal.terminal import error, info, warn
from rttools.modules.instances.routing import getNumFlits
from rttools.modules.instances import release
import networkx as nx
import copy

def createInstance(app, noc, frequency):

  # convert seconds into cycles (frequency divided by one second)
  # division intended, do not remove
  scale = frequency / 1 

  tasks = []
  flows = []

  # copy nodes to instance (nothing to do for nodes)
  for n in app.nodes(data=True):
    id, data = n

    tasks.append((id, {
      #'label'   : data['label'],
      'wcet'  : data['wcet']
    }))

  # copy edges to instance
  # - adjust period and deadline to cycles
  # - adjust data accordingly to routing rules
  for e in app.edges(data=True):
    source, target, data = e
    
    flows.append((
      source,
      target,
      {
        'label'   : data['label'] ,
        'period'  : int(float(data['period']) * scale),
        'datasize': data['datasize'],
        'deadline': int(float(data['deadline']) * scale)
      }
    ))

  # release model of the flows and its parameters (release.py); the
  # task wcet is the cost c^(v) of the task in cycles
  return {
    'tasks': tasks, 
    'flows' : flows,
    'release': release.settings(getattr(app, 'graph', {}) or {})
  }