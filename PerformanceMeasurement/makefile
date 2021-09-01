OPT_CUDA_DIR = /opt/cuda
ifeq (${OPT_CUDA_DIR}, ${wildcard ${OPT_CUDA_DIR}})
#目录存在
	CUDA_DIR = ${OPT_CUDA_DIR}
else
#目录不存在
endif

LOCAL_CUDA_DIR = /usr/local/cuda
ifeq (${LOCAL_CUDA_DIR}, ${wildcard ${LOCAL_CUDA_DIR}})
#目录存在
	CUDA_DIR = ${LOCAL_CUDA_DIR}
endif

CUDA_INC = $(CUDA_DIR)/include
CUDA_GDK = $(CUDA_DIR)/gdk
CUDA_LIB = $(CUDA_DIR)/lib64
CUDA_STUBS = $(CUDA_DIR)/lib64/stubs

# POWER_MANAGER_DIR := /home/wfr/work/Energy/PowerManager
# POWER_MANAGER_SRC := ${POWER_MANAGER_DIR}/PowerManager.cpp

CC = g++
# CFLAGS = -Wall -g -O0 -Wno-unused-parameter
CFLAGS = -Wall -O3 -Wno-unused-parameter
SPECIALFLAGS = -lnvidia-ml -lpthread
# CXX_LIB_DIR = /home/wfr/install/GCC-8/install/lib64
# CXX_INC_DIR = /WORKSPACE/wfr/install/GCC-8/install/include/c++/8.3.0
RPATH = -Wl,-rpath=${CXX_LIB_DIR}

SRC = main.cpp PowerManager.cpp
APP_SRC = App.cpp Msg2EPRT.cpp
TARGET = PerfMeasure

all: $(TARGET)

$(TARGET): $(SRC)
	$(CC) $(CFLAGS) -I$(CUDA_INC) -I$(CUDA_GDK) -L$(CUDA_LIB) -L$(CUDA_STUBS) -lcudart -lcuda $(SPECIALFLAGS) -o $@.bin $(SRC)

app:
	$(CC) $(CFLAGS) -lpthread -o $@.bin ${APP_SRC}

mytest:
	$(warning, "test00")
	$(warning, "${CUDA_DIR}")
	@echo "${CUDA_DIR}"

gdb:
	gdb ./$(TARGET).bin

clean:
	rm -f *.o *.bin