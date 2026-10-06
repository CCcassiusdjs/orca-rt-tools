
from sys import argv
from rttools.log2gannt.matplot import l2g_main

if __name__ == "__main__":
	
  if len(argv) < 2:
    print("USAGE: log-gannt <logfile> [--map <json>] [--out <png>] [--units-per-ms <n>]")
  else:
	  l2g_main(argv[1::])
