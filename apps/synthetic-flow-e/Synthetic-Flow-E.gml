graph [
  directed 1
  node [
    id 0
    label "Task A"
    period 10
    capacity 10
    deadline 10
  ]
  node [
    id 1
    label "Task B"
    period 10
    capacity 10
    deadline 10
  ]
  
  edge [
    id 0
    source 0
    target 1
    label "f1"
    period 10
    datasize 10
    deadline 10
  ]
  edge [
    id 1
    source 0
    target 1
    label "f2"
    period 10
    datasize 10
    deadline 10
  ]
]
