OPT_CUDA_DIR = /opt/cuda
ifeq (${OPT_CUDA_DIR}, ${wildcard ${OPT_CUDA_DIR}})
	CUDA_DIR = ${OPT_CUDA_DIR}
endif

LOCAL_CUDA_DIR = /usr/local/cuda
ifeq (${LOCAL_CUDA_DIR}, ${wildcard ${LOCAL_CUDA_DIR}})
	CUDA_DIR = ${LOCAL_CUDA_DIR}
endif

CUDA_INC = $(CUDA_DIR)/include
CUDA_GDK = $(CUDA_DIR)/gdk
CUDA_LIB = $(CUDA_DIR)/lib64
CUDA_STUBS = $(CUDA_DIR)/lib64/stubs

CC = g++
CFLAGS = -Wall -O3 -Wno-unused-parameter
SPECIALFLAGS = -lnvidia-ml -lpthread

SRC = ../main.cpp ../PowerManager.cpp
TARGET = PerfMeasure

all: $(TARGET)

$(TARGET): $(SRC)
	$(CC) $(CFLAGS) -I$(CUDA_INC) -I$(CUDA_GDK) -L$(CUDA_LIB) -L$(CUDA_STUBS) -lcudart -lcuda $(SPECIALFLAGS) -o $@.bin $(SRC)

clean:
	rm -f *.o *.bin
	