from rttools.terminal.terminal import error 
from os.path import exists as file_exists
import json
import sys 
sys.path.append('../lib')

def loadFromFile(conf_file_name):

  if not file_exists(conf_file_name):
    # error('Unable to load configuration file. Could not locate file "' + conf_file_name + '".')
    # exit(1)
    pass
  else: 
    #with open(conf_file_name) as f:
    #  lines = f.read()
    #  return json.loads(lines)
    pass