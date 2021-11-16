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
CUPTI_INCS = -I/opt/cuda/include -I/opt/cuda/extras/CUPTI/include

CC = g++
DEBUG_FLAGS = -g -O3
CFLAGS = ${DEBUG_FLAGS}
PIC_FLAG = -Xcompiler -fPIC
NVIDIA_LIBS = -L${CUDA_DIR}/extras/CUPTI/lib64 -lcudart -lcuda -lnvidia-ml -lpthread -lcupti -lnvperf_target -lnvperf_host
INCS = -I.
PY_LIBS = -lpython3.7m
PY_INC = /home/user/.conda/envs/my_env/include/python3.7m
PYBIND11_LIBS = 
PYBIND11_INC = /home/user/.conda/envs/my_env/include
PY_LIB = /home/user/.conda/envs/my_env/lib

POWER_INC = ../../PerformanceMeasurement
SRC = ../EPOpt.cpp ../List.cpp ../Metric.cpp ../Eval.cpp ../PowerManager.cpp ../PowerMeasure.cpp ../Py2EPOpt.cpp
PY2CPP_OBJ = Py2EPOpt.o
OBJ = $(SRC:.cpp=.o)
TARGET = EPOptDrv

all: $(TARGET)

$(TARGET): $(OBJ)
	nvcc -o $@.so $^ $(CFLAGS) -shared ${INCS} -I$(CUDA_INC) -I$(CUDA_GDK) -I${PY_INC} -I${PYBIND11_INC} -L$(CUDA_LIB) -L$(CUDA_STUBS) -L${PY_LIB} $(NVIDIA_LIBS)

PowerManager.o: ${POWER_INC}/PowerManager.cpp
	nvcc -o $@ -c $< $(CFLAGS) ${PIC_FLAG} ${INCS} -I$(POWER_INC) -I$(CUDA_INC) -I$(CUDA_GDK) $(CUPTI_INCS)

${PY2CPP_OBJ}: Py2EPOpt.cpp
	nvcc -o $@ -c $< -O3 ${PIC_FLAG} ${INCS} -I$(POWER_INC) -I$(CUDA_INC) -I$(CUDA_GDK) $(CUPTI_INCS) -I${PY_INC} -I${PYBIND11_INC}

%.o: %.cpp
	nvcc -o $@ -c $< $(CFLAGS) ${PIC_FLAG} ${INCS} -I$(POWER_INC) -I$(CUDA_INC) -I$(CUDA_GDK) $(CUPTI_INCS)

clean:
	rm -f *.so *.o *.bin