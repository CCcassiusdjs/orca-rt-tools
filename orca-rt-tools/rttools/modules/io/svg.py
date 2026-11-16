import random

# fixed seed: the same input produces the same SVG
SVG_COLOR_SEED = 0


def getColor(rng=random):
    r = lambda: rng.randint(150, 220)
    return "#{:02x}{:02x}{:02x}".format(r(), r(), r())


def saveSvg(filename, res, problem, skipped=[], scale_x=1):
    # SCALE_X = 1/100
    SCALE_X = scale_x
    SCALE_Y = 1
    SCALE_TICKS = int(100 / SCALE_X)
    RECT_HEIGHT = 10 * SCALE_Y
    RECT_WIDTH = SCALE_X
    LEFT_PADDING = 14
    BARS_PADDING = 50
    BARS_HEIGHT = (len(problem["links"]) + 1) * RECT_HEIGHT

    docWidth = problem["hyperperiod"] * SCALE_X + 200
    docHeight = len(problem["links"]) * 10

    f = open(filename, "w")
    f.write(
        '<svg version="1.1" width="'
        + str(docWidth)
        + '" height="'
        + str(docHeight * 2 + 200)
        + '" xmlns="http://www.w3.org/2000/svg">\n'
    )
    f.write('<style> text { font-family: "Arial"; }</style>')

    # background
    f.write(
        '<rect width="'
        + str(problem["hyperperiod"] * RECT_WIDTH)
        + '" height="'
        + str(BARS_HEIGHT - RECT_HEIGHT)
        + '" x="'
        + str(BARS_PADDING)
        + '" y="0" fill="#eee" />\n'
    )

    # get colors for each packet
    colors = []
    rng = random.Random(SVG_COLOR_SEED)
    for i in range(0, len(problem["packets"])):
        colors.append(getColor(rng))

    # left scale here
    for l in range(0, len(problem["links"])):
        src, trg, data = problem["links"][l]
        f.write(
            '<text x="'
            + str(LEFT_PADDING)
            + '" y="'
            + str(l * RECT_HEIGHT + RECT_HEIGHT - 1)
            + '" font-size="10px">'
            + data["label"]
            + "</text>\n"
        )
    f.write(
        '<text x="10" transform="rotate(90,3,0)" y="0" font-size="10px">links</text>\n'
    )

    # print packets
    for l in range(0, len(res)):
        for p in range(0, len(res[0])):
            name = problem["packets"][p]["name"]

            if res[l][p] != None:
                x = res[l][p] * RECT_WIDTH + BARS_PADDING  # left scale width
                y = l * RECT_HEIGHT

                width = problem["occupancy"][l][p] * RECT_WIDTH
                height = RECT_HEIGHT

                # print(x, y, width, height, name, colors[p])

                f.write(
                    '<rect width="'
                    + str(width)
                    + '" height="'
                    + str(height)
                    + '" x="'
                    + str(x)
                    + '" y="'
                    + str(y)
                    + '" fill="'
                    + colors[p]
                    + '" />\n'
                )
                f.write(
                    '<text width="'
                    + str(width)
                    + '" height="'
                    + str(height)
                    + '" x="'
                    + str(x)
                    + '" y="'
                    + str(y + 8)
                    + '" font-size="10px">'
                    + name
                    + "</text>\n"
                )

    # bottom scale
    y = len(res) * RECT_HEIGHT + 10
    f.write(
        '<text x="'
        + str(i + BARS_PADDING)
        + '" y="'
        + str(y + 40)
        + '" font-size="10px">time (cycles)</text>\n'
    )
    for i in range(0, problem["hyperperiod"], SCALE_TICKS):
        f.write(
            '<rect width="1" height="20" x="'
            + str(i * SCALE_X + BARS_PADDING)
            + '" y="'
            + str(y)
            + '" fill="#666" />\n'
        )
        f.write(
            '<text x="'
            + str(i * SCALE_X + BARS_PADDING + 3)
            + '" y="'
            + str(y + 20)
            + '" font-size="10px">'
            + str(i)
            + "</text>\n"
        )
    f.write

    # add hyperperiod information
    f.write(
        '<rect width="1" height="20" x="'
        + str(problem["hyperperiod"] * RECT_WIDTH + BARS_PADDING)
        + '" y="'
        + str(y)
        + '" fill="blue" />\n'
    )
    f.write(
        '<text x="'
        + str(problem["hyperperiod"] * RECT_WIDTH + BARS_PADDING + 2)
        + '" y="'
        + str(y + 20)
        + '" fill="blue" font-size="10px">'
        + str(problem["hyperperiod"])
        + "</text>\n"
    )

    # not scheduled packets
    base = y + 70
    t = 10
    i = 0

    # @todo to be removed
    skipped = []

    for p in skipped:
        name = problem["packets"][p]["name"]
        f.write(
            '<text x="'
            + str(LEFT_PADDING)
            + '" y="'
            + str(base + t * i)
            + '" font-size="10px">'
            + name
            + "</text>\n"
        )

        links = []

        # print problematic link data
        for l in range(0, len(problem["links"])):
            if problem["occupancy"][l][p] != None:
                width = problem["occupancy"][l][p] * SCALE_X
                source, target, data = problem["links"][l]
                link_name = data["label"]

                links.append(l)  # save links for below plot
                x = problem["min_start"][l][p] + BARS_PADDING  # left scale width

                f.write(
                    '<rect width="'
                    + str(width)
                    + '" height="'
                    + str(RECT_HEIGHT)
                    + '" x="'
                    + str(BARS_PADDING)
                    + '" y="'
                    + str(base + i * t + 1)
                    + '" fill="'
                    + colors[p]
                    + '" style="fill-opacity: .5;" />\n'
                )
                f.write(
                    '<text width="'
                    + str(width)
                    + '" height="'
                    + str(RECT_HEIGHT)
                    + '" x="'
                    + str(BARS_PADDING)
                    + '" y="'
                    + str(base + i * t + 10)
                    + '" font-size="10px">'
                    + link_name
                    + "</text>\n"
                )
                i += 1

        # print(links)

        # repeat previous lines
        for l in links:
            for p in range(0, len(res[0])):
                name = problem["packets"][p]["name"]

                if res[l][p] != None:
                    x = res[l][p] * RECT_WIDTH + BARS_PADDING  # left scale width
                    y = l * RECT_HEIGHT

                    width = problem["occupancy"][l][p] * RECT_WIDTH
                    height = RECT_HEIGHT

                    f.write(
                        '<rect width="'
                        + str(width)
                        + '" height="'
                        + str(height)
                        + '" x="'
                        + str(x)
                        + '" y="'
                        + str(base + i * t + 1)
                        + '" fill="'
                        + colors[p]
                        + '" />\n'
                    )
                    f.write(
                        '<text width="'
                        + str(width)
                        + '" height="'
                        + str(height)
                        + '" x="'
                        + str(x)
                        + '" y="'
                        + str(base + i * t + 10)
                        + '" font-size="10px">'
                        + name
                        + "</text>\n"
                    )
            i += 1

        i += 5
    f.write("</svg>\n")
    f.close()

    return
