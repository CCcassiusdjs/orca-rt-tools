int: num_packets;
int: num_links;
int: hp;

set of int: PACKETS = 1..num_packets;
set of int: LINKS = 1..num_links;

% maximum "end" execution time
array[LINKS, PACKETS] of -1..hp: deadline; 

% prevents packet overleap
array[LINKS, PACKETS] of -1..hp: min_start;   

% time taken per link
array[LINKS, PACKETS] of -1..hp: occupancy;   

% answer, output
array[LINKS, PACKETS] of var -2..hp: release_time;  

% cannot release packets before their release time, 
% and cannot release them after their deadline (lower bound rule)
constraint forall(l in LINKS, p in PACKETS where min_start[l, p] > -1)(
  release_time[l, p] >= min_start[l, p] /\  release_time[l, p] + occupancy[l, p] <= hp
);
  
% packet must be transmitted before its deadline (upper bound rule)
constraint forall(l in LINKS, p in PACKETS where occupancy[l, p] > -1)(
  release_time[l, p] + occupancy[l, p] <= deadline[l, p]
);

% force all links to be allocated during the same time slice
% assumption: the whole channel is allocated during the whole transmission
% replacement: link allocation time is T' = T + 4, link close time is unknown
constraint forall(p in PACKETS, l1 in LINKS, l2 in LINKS where deadline[l1, p] > -1 /\ deadline[l2, p] > -1)(
  release_time[l1, p] = release_time[l2, p]
);

% definition of overleap predicate (same as in job shop)
predicate nonoverlap(
  var int:b1, % begin of span 1
  var int:e1, % duration of span 1
  var int:b2, % begin of span 2
  var int:e2  % duration of span 2
) = b1 + e1 < b2 \/ b2 + e2 < b1;

% prevent two flow from sharing the same resource at the same time (uses the predicate above)
constraint forall(p1 in PACKETS, p2 in PACKETS, l in LINKS where p1 != p2 /\ deadline[l, p1] > -1 /\ deadline[l, p2] > -1)( 
   nonoverlap(
     release_time[l, p1], occupancy[l, p1], 
     release_time[l, p2], occupancy[l, p2] 
   )
);

solve satisfy;

output [show_int(2, release_time[l,p]) ++ if p = num_packets then "\n" else "\t" endif | l in LINKS, p in PACKETS]; 


constraint forall(l in LINKS, p in PACKETS where min_start[l, p] = -1)(
  release_time[l, p] = -1
);