graph [
  directed 1
  node [
    id 0
    label "AFA"
    alias "AnonFilterA"
    period 78651
    capacity 36480
    deadline 36480
  ]
  node [
    id 1
    label "IDNT"
    alias "Identity"
    period 78651
    capacity 384
    deadline 53905
  ]
  node [
    id 2
    label "DCT"
    alias "DCT_2D"
    period 78651
    capacity 16032
    deadline 53378
  ]
  node [
    id 3
    label "SPL"
    alias "Splitter"
    period 78651
    capacity 576
    deadline 37203
  ]
  node [
    id 4
    label "IDC"
    alias "iDCT_2D"
    period 78651
    capacity 16032
    deadline 69553
  ]
  node [
    id 5
    label "JOIN"
    alias "Joiner"
    period 78651
    capacity 768
    deadline 70400
  ]
  node [
    id 6
    label "AFB"
    alias "AnonFilterB"
    period 78651
    capacity 44
    deadline 78651
  ]
  edge [
    source 0
    target 3
    label "f1"
    period 78651
    datasize 4096
    deadline 36627
  ]
  edge [
    source 1
    target 5
    label "f7"
    period 78651
    datasize 4096
    deadline 70253
  ]
  edge [
    source 3
    target 2
    label "f2"
    period 78651
    datasize 4096
    deadline 37346
  ]
  edge [
    source 3
    target 1
    label "f6"
    period 78651
    datasize 4096
    deadline 53521
  ]
  edge [
    source 2
    target 4
    label "f3"
    period 78651
    datasize 4096
    deadline 53521
  ]
  edge [
    source 4
    target 5
    label "f4"
    period 78651
    datasize 64
    deadline 69632
  ]
  edge [
    source 5
    target 6
    label "f5"
    period 78651
    datasize 8192
    deadline 78607
  ]
]
