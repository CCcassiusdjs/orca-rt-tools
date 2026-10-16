DEFS := -DNO_TTY_COLORSdd

CC := g++
CFLAGS := -O3 -g -Wall $(DEFS)

SRCS := $(wildcard **/*.cpp)
OBJS := $(patsubst %.cpp,%.o,$(SRCS))

TARGET := porca


all: $(TARGET)
	@echo "... Collecting sources:" $(SRCS)
	@echo "... Generating objects:" $(OBJS)
	./porca -porca po -g x -i 9 -90 -50 -gg
#
$(TARGET): $(OBJS)
	$(CC) $(CFLAGS) -o $@ $^


# 
%.o: %.cpp
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -rf $(OBJS) $(TARGET)


.PHONY: all clean
