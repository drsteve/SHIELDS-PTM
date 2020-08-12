PYEXE = `which python3`
PROG = ptm
F90 = gfortran
OPT = -ffree-form -ffree-line-length-none -std=f2008ts -fopenmp -O3

SRCS := $(wildcard src/*.f90)
OBJS := $(patsubst %.f90,%.o,$(SRCS))
PRG_OBJ = $(PROG).o

# First target is default on calling `make` w/o args
all: ptm python

# Compile all objects
$(OBJS): %.o : %.f90
	$(F90) $(OPT) -c -o $@ $<

# Link everything
$(PROG): $(OBJS)
	$(F90) $(OPT) -o $@ $^

# Explicitly list dependencies (will control compile/link order)
src/rksuite.o :
src/global.o : src/rksuite.o
src/fields.o : src/global.o src/finite_differences.o src/interpolation.o
src/fileio.o : src/global.o src/particles.o src/fields.o
src/finite_differences.o: src/global.o
src/pusher.o: src/global.o src/particles.o src/fields.o
src/particles.o: src/global.o src/fields.o src/interpolation.o
src/ptm.o : src/pusher.o src/fileio.o

python:
	$(PYEXE) setup.py install

clean: clean-ptm clean-python

clean-ptm:
	rm -f src/*.o
	rm -f *.mod
	rm -f ptm

clean-python:
	rm -f ptm_python/*.pyc
	rm -rf ptm_python/__pycache__
