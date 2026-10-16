# generate string of whitespaces
def genwss(len):
  buf = ""
  i = 0
  for i in range(i, len):
    buf = buf + ' '
  return buf

# zero fill
def wsfill(num, pad):
  nstr = str(num)
  fill = genwss(pad - len(nstr))
  return fill + nstr
