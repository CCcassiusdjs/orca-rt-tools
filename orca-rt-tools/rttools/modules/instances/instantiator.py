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
  instance = {
    'tasks': tasks, 
    'flows' : flows,
    'release': release.settings(getattr(app, 'graph', {}) or {})
  }

  # end-to-end deadline of each task in cycles (Deadline column of the task
  # rows; release.deadline_fits)
  deadlines = (getattr(app, 'graph', {}) or {}).get('task_deadlines')
  if deadlines:
    instance['deadlines'] = {t: int(float(d) * scale) for t, d in deadlines.items()}

  # phase model with several periods or a cycle (rttools/bench_t/
  # multirate.py): the period of each flow is m_e k_u phases of
  # floor(P f) cycles, so the periods share the phase in cycles
  if instance['release']['model'] == release.PHASE:
    from rttools.bench_t import multirate
    rates = multirate.instance_rates(app, frequency)
    if rates is not None:
      by_label = {d['label']: (s, d) for s, _, d in flows}
      for label, (s, d) in by_label.items():
        d['period'] = rates['flow_jobs'][label] * rates['ticks'][s] * rates['phase_cycles']
      instance['rates'] = rates
  return instance