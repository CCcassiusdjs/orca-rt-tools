from pktgen import pktGen
from terminal import header
# app entry-point
def rttool(appfile, mapfile, archfile):
  header("Welcome to RT_TOOLS r0.0.0.1-alpha")
  x = pktGen(appfile, mapfile, archfile)
