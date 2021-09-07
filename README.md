# GPOEO
a micro-intrusive GPU online energy optimization (GPOEO) framework for iterative applications

1. EPOpt contains source code of the GPOEO

1. PerformanceMeasurement (PerfMeasure) is a NVIDIA GPU measurer for energy/power/utilities/clocks

## Make GPOEO
cd EPOpt && mkdir build && cp makefile ./build
cd build && make

## Make PerfMeasure
cd PerformanceMeasurement && mkdir build && cp makefile ./build
cd build && make

## Use GPOEO in python applications
GPOEO only has two APIs: Begin(args) and End(). 
The two APIs should be inserted at the beginning and end of the main python file respectively.
As shown below:
```
from PyEPOpt import EPOpt

if __name__=="__main__":
    EPOpt.Begin(GPUID4CUDA, GPUID4NVML, RunMode, MeasureOutDir, ModelDir, TestPrefix)

    .....

    EPOpt.End()
```
