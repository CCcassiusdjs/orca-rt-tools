graph [
  directed 1
  channelWidth 4
  node [
    id 0
    label "0"
    X 0
    Y 0
  ]
  node [
    id 1
    label "1"
    X 1
    Y 0
  ]
  node [
    id 2
    label "2"
    X 0
    Y 1
  ]
  node [
    id 3
    label "3"
    X 1
    Y 1
  ]

  edge [
    source 0
    target 1
    label "0-1"
  ]
  edge [
    source 0
    target 2
    label "0-2"
  ]
  edge [
    source 1
    target 3
    label "1-3"
  ]
  edge [
    source 2
    target 3
    label "2-3"
  ]

  edge [
    source 1
    target 0
    label "1-0"
  ]
  edge [
    source 2
    target 0
    label "2-0"
  ]
  edge [
    source 3
    target 1
    label "3-1"
  ]
  edge [
    source 3
    target 2
    label "3-2"
  ]
]