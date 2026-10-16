
def get_largest_path(n, dct, graph):
    
    # if processed already, return value
    if n in dct.keys():
        return dct[n]
    
    dct[n] = -1 # flag to avoid cycles

    # find all "antecessors" of n
    ante = []
    ante_sum = 0
    for e in graph._edges:
        if e._to == n:
            ante.append(e._from)
            ante_sum = ante_sum + int(e._data["payload"])

    # find get the maximum path to 
    max_distance = 0
    max_distance_node = None

    for nn in ante:
        dist = get_largest_path(nn, dct, graph)
        if(dist == -1):
            continue

        if(dist > max_distance):
            max_distance = dct[nn]
            max_distance_node = nn

    dct[n] = max_distance + int(n._data["wcet"]) + ante_sum
    return dct[n]


def calculate_gcpa(graph):
    
    dct = {}

    # while len(dct.keys()) < len(graph._nodes):
    #   for n in graph._nodes:
    #       if n not in dct.keys():
    #           get_largest_path(n, dct, graph)
    for n in graph._nodes:
      get_largest_path(n, dct, graph)

    return dct

def cluster_time(costs):
    """CPU time of the task set of one PE by the CPA rule of ORT/GCPA
    (ORCA RT-Tools reference, Sec. 8.1.4): the driver operations of one
    processor cannot run in parallel, so the method sums the costs of the
    tasks of the set in place of the longest path between them.
    `costs`: iterable of task costs in cycles (int >= 0), each with the
    kernel work of the task. Returns the cycles of one iteration."""
    total = 0
    for c in costs:
        v = int(c)
        if (isinstance(c, float) and c != v) or v < 0:
            raise ValueError(f"cost must be a non-negative integer, got {c!r}")
        total += v
    return total
