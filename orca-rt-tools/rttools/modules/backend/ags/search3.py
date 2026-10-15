"""Adaptive Guided Search (AGS): Fig. 6.6 of the ORCA RT-Tools reference (2024)
and Fig. 3 of Domingues et al., ICECS 2022.

Published pseudocode, as this module reads it:

    R <- packets in the order of the criterion (LSTF, MBCF or MCPF)
    Q <- empty ordered set; S <- {} (skipped); F <- PF; G <- threshold
    T <- zeros (failures per packet)
    while |R| != 0:
        schedule <- {}; for q in Q: allocate(schedule, q, F)    (reset)
        for r in R:
            if not allocate(schedule, r, F):
                T[r] <- T[r] + 1
                if T[r] < G: R.push_front(r); goto reset
                else: R.remove(r); S.push(r)
        return schedule, S

Reading adopted where the pseudocode leaves room:

- allocate(schedule, r, F) places packet r alone (first fit) and never
  moves a placed packet: it tries the releases a, a + F, a + 2F, ... of
  the window [a, b] of r, with b = deadline - occupancy, truncated at b
  (b is the last candidate when it is not on the grid, as in Fig. 6.5),
  and keeps the first release whose interval [k, k + o] overlaps no
  placed packet on any link of the path of r (closed intervals, as the
  collision test of Sec. 6.3.1).
- push_front moves r to the front of R (R holds each packet once).
- The jump after a failure goes to the reset (line 10 of Fig. 6.6) and
  keeps T. The jump to line 7 of the figure passes line 8, which zeroes
  T; with T zeroed, a packet that never fits makes the search loop
  forever, and the text counts the tries of each packet across resets.
- No line of the pseudocode inserts into Q, so the partial schedule of
  lines 11 to 13 is empty and every reset starts from an empty schedule.
- After a packet reaches G failures, it leaves R into S and the pass
  continues with the next packet (pseudocode, lines 20 and 21).
- The search returns when a pass reaches the end of R.

Each reset follows a failure with T[r] < G, so a run has at most
|P| (G - 1) resets.

Counters (module attribute `hsearch`, read by rttools.paper.ch6 and the
TUI): entered = calls to allocate plus one per run for the final node
(the depth-first search before counted its leaf node the same way);
ignored = candidate releases rejected by the collision test; skipped =
packets in S; resets = number of resets.
"""
from types import SimpleNamespace

from rttools.terminal.terminal import debug, error, info, warn

# search counters of the last run
hsearch = SimpleNamespace(entered=0, ignored=0, skipped=[], resets=0)


'''
Checks whether two ranges overleap.
@param ra range a, the first range
@param rb range b, the second range
@returns True if the ranger overleap, otherwise False

'''
def overleap(ra, rb):
  mina, maxa = ra
  minb, maxb = rb

  return not(maxa < minb or maxb < mina)


def candidates(a, b, step):
  """Releases a, a + step, ... up to b, with b itself as the last
  candidate (truncation at the maximum release). Empty when b < a."""
  if b < a:
    return []
  ks = list(range(a, b + 1, step))
  if ks[-1] != b:
    ks.append(b)
  return ks


def packet_view(p, j):
  """Links, occupancy and release window [a, b] of packet j."""
  links = [l for l in range(len(p['occupancy'])) if p['occupancy'][l][j] is not None]
  if not links:
    return [], 0, 0, 0   # no link: nothing to reserve
  l0 = links[0]
  o = p['occupancy'][l0][j]
  a = p['min_start'][l0][j]
  b = p['deadline'][l0][j] - o
  return links, o, a, b


def allocate(placed, view, step):
  """First release of the window of the packet whose interval overlaps no
  interval in `placed` (link -> list of (start, end)) on its links, or
  None. Counts the rejected candidates in hsearch.ignored."""
  links, o, a, b = view
  for k in candidates(a, b, step):
    rng = (k, k + o)
    if any(overleap(rng, iv) for l in links for iv in placed[l]):
      hsearch.ignored += 1
      continue
    return k
  return None


def search3(p, heuristic, tries, step):
  """Runs the AGS on problem `p` (tables link x packet min_start,
  occupancy and deadline) with the order of `heuristic`, threshold G =
  `tries` and pruning factor PF = `step`.

  Returns (schedule, skipped): schedule is a link x packet table with the
  release of each placed packet on the links of its path (None
  elsewhere and for skipped packets); skipped is the set S of packet
  indices that reached G failures."""
  hsearch.entered = 0
  hsearch.ignored = 0
  hsearch.skipped = []
  hsearch.resets = 0

  nlinks = len(p['occupancy'])
  npackets = len(p['occupancy'][0]) if nlinks else 0
  views = [packet_view(p, j) for j in range(npackets)]

  # order of the criterion (rttools/modules/backend/ags/heuristics.py)
  R = list(heuristic(p))
  S = []
  T = [0 for _ in range(npackets)]

  while True:
    # reset: empty schedule (Q is empty)
    placed = [[] for _ in range(nlinks)]
    release = {}
    failed = None
    i = 0
    while i < len(R):
      r = R[i]
      hsearch.entered += 1
      k = allocate(placed, views[r], step)
      if k is not None:
        release[r] = k
        for l in views[r][0]:
          placed[l].append((k, k + views[r][1]))
        i += 1
        continue
      T[r] += 1
      name = p['packets'][r]['name'] if isinstance(p['packets'][r], dict) else str(p['packets'][r])
      if T[r] < tries:
        debug("Could not schedule " + name + " (" + str(T[r]) + "/" + str(tries) + "); reset.")
        failed = r
        break
      error("Could not schedule " + name + " after " + str(T[r]) + " tries; skipped.")
      R.pop(i)
      S.append(r)
    if failed is None:
      break
    R.remove(failed)
    R.insert(0, failed)
    hsearch.resets += 1

  hsearch.entered += 1
  hsearch.skipped = list(S)

  sched = [[None for _ in range(npackets)] for _ in range(nlinks)]
  for r, k in release.items():
    for l in views[r][0]:
      sched[l][r] = k

  info("AGS finished: " + str(len(release)) + " packets placed, " + str(len(S)) + " skipped, "
       + str(hsearch.resets) + " resets")
  info("Ignored nodes: " + str(hsearch.ignored))
  info("Entered nodes: " + str(hsearch.entered))
  return (sched, set(S))
