from math import ceil
from gcm.terminal import header, info


class TraceDoc():
    _elems = []
    _width = 50000
    _height = 5000

    def __init__(self, fx, fy):
        self._FACTOR_X = fx
        self._FACTOR_Y = fy

    def svg_rule(self):
        rule = []

        RULE_STEP = 500

        for i in range(0, self._width, ceil(self._width/RULE_STEP)):
            rule.append(f'<rect x="{i}" y="0" width="1" height="1000" ')
            rule.append('fill="#aaa"></rect>')

            rule_y = int(i) * self._FACTOR_X
            rule.append(f'<text fill="#aaa" x="{i+2}" y="20">{rule_y}</text> ')

        return "".join(rule)

    def __str__(self):
        ss = f'<svg version="1.1" width="{self._width}" '
        ss = ss + f'height="{self._height}" '
        ss = ss + 'xmlns="http://www.w3.org/2000/svg">\n'

        ss = ss + '<style> text { font-family: Helvetica; } </style>\n'

        ss = ss + self.svg_rule()

        for e in self._elems:
            ss = ss + str(e)

        ss = ss + "</svg>\n"
        return ss


class TraceElem():
    _x: int
    _y: int
    _width: int
    _height: int
    _color: str
    _font: str
    _text: str

    def __str__(self):
        ss = f'<rect fill="{self._color}" width="{self._width}" '
        ss = ss + f'height="{self._height}" x="{self._x}" y="{self._y}"></rect> '
        ss = ss + f'<text fill="{self._font}" x="{self._x + 2}" y="{self._y + 16}"> '
        ss = ss + f'{self._text}</text>\n'
        return ss




    # SCALE_FACTOR_X = 50

    # trace_num = 0

    # # create new tracedoc
    # doc: TraceDoc = TraceDoc(SCALE_FACTOR_X, 0)



#         trace_num = trace_num + 1

# # get project name
# v = trace_files[0].split('.')[0]

# # save to file
# with open(v + (".svg"), "w+") as svg:
#     svg.write(str(doc))


def print_trace():
    trace_height = trace_num * 150

    y = 20 + trace_height
    # print tasks, kernel, and driver
    for t in trace_infos:
        elem = TraceElem()
        elem._x = int(t["start"]) / SCALE_FACTOR_X
        elem._height = 20
        elem._text = t["data"]

        if (t["type"] == 'SystemEventType.KERNEL_TIME'):
            elem._width = kernel_info.SCHEDULE_IRQ_WCET / SCALE_FACTOR_X
            elem._color = "black"
            elem._font = "white"
            elem._y = y + 20

        elif (t["type"] == 'SystemEventType.APP_TIME'):
            elem._width = kernel_info.SCHEDULE_APP_TIME / SCALE_FACTOR_X
            elem._color = "blue"
            elem._font = "white"
            elem._y = y + 40

        elif (t["type"] == 'SystemEventType.SEND_ISR'):
            elem._width = 5
            elem._color = "green"
            elem._font = "black"
            elem._y = y + 60

        else:
            elem._width = 5
            elem._color = "red"
            elem._font = "black"
            elem._y = y + 60

        doc._elems.append(elem)
        print(elem)


