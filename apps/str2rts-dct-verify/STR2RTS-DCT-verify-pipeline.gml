graph [
  directed 1
  node [
    id 0
    label "AFA"
    alias "AnonFilterA"
    period 40000
    capacity 36480
    deadline 40000
  ]
  node [
    id 1
    label "IDNT"
    alias "Identity"
    period 40000
    capacity 384
    deadline 40000
  ]
  node [
    id 2
    label "DCT"
    alias "DCT_2D"
    period 40000
    capacity 16032
    deadline 40000
  ]
  node [
    id 3
    label "SPL"
    alias "Splitter"
    period 40000
    capacity 576
    deadline 40000
  ]
  node [
    id 4
    label "IDC"
    alias "iDCT_2D"
    period 40000
    capacity 16032
    deadline 40000
  ]
  node [
    id 5
    label "JOIN"
    alias "Joiner"
    period 40000
    capacity 768
    deadline 40000
  ]
  node [
    id 6
    label "AFB"
    alias "AnonFilterB"
    period 40000
    capacity 44
    deadline 40000
  ]
  edge [
    source 0
    target 3
    label "f1"
    period 40000
    datasize 4096
    deadline 40000
  ]
  edge [
    source 1
    target 5
    label "f7"
    period 40000
    datasize 4096
    deadline 40000
  ]
  edge [
    source 3
    target 2
    label "f2"
    period 40000
    datasize 4096
    deadline 40000
  ]
  edge [
    source 3
    target 1
    label "f6"
    period 40000
    datasize 4096
    deadline 40000
  ]
  edge [
    source 2
    target 4
    label "f3"
    period 40000
    datasize 4096
    deadline 40000
  ]
  edge [
    source 4
    target 5
    label "f4"
    period 40000
    datasize 64
    deadline 40000
  ]
  edge [
    source 5
    target 6
    label "f5"
    period 40000
    datasize 8192
    deadline 40000
  ]
]
