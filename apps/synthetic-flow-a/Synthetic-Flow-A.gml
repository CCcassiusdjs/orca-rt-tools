graph [
  directed 1
  node [
    id 0
    label "Task A"
    period 55
    capacity 20
    deadline 55
  ]
  node [
    id 1
    label "Task B"
    period 55
    capacity 20
    deadline 55
  ]
  node [
    id 2
    label "Task C"
    period 55
    capacity 20
    deadline 55
  ]
  node [
    id 3
    label "Task D"
    period 55
    capacity 20
    deadline 55
  ]

  edge [
    source 0
    target 1
    label "f1"
    period 55
    datasize2 160
    datasize 20
    deadline 55
  ]
  edge [
    source 0
    target 3
    label "f2"
    period 55
    datasize2 416
    datasize 52
    deadline 55
  ]
  edge [
    source 2
    target 3
    label "f3"
    period 55
    datasize2 192
    datasize 24
    deadline 55
  ]
  edge [
    source 2
    target 1
    label "f4"
    period 55
    datasize2 256
    datasize 32
    deadline 55
  ]
  edge [
    source 3
    target 0
    label "f5"
    period 55
    datasize2 128
    datasize 16
    deadline 55
  ]
]