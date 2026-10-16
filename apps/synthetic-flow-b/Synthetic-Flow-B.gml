graph [
  directed 1
  node [
    id 0
    label "Task A"
    period 60
    capacity 30
    deadline 60
  ]
  node [
    id 1
    label "Task B"
    period 60
    capacity 30
    deadline 60
  ]
  node [
    id 2
    label "Task C"
    period 20
    capacity 10
    deadline 20
  ]
  node [
    id 3
    label "Task D"
    period 30
    capacity 15
    deadline 30
  ]
  edge [
    id 0
    source 0
    target 1
    label "f1"
    period 60
    datasize 128
    deadline 50
  ]
  edge [
    source 0
    target 3
    label "f2"
    period 60
    datasize 128
    deadline 55
  ]
  edge [
    source 2
    target 3
    label "f3"
    period 20
    datasize 128
    deadline 20
  ]
  edge [
    source 2
    target 1
    label "f4"
    period 30
    datasize 128
    deadline 28
  ]
  edge [
    source 3
    target 0
    label "f5"
    period 30
    datasize 128
    deadline 30
  ]
]
