# GPOEO
GPOEO is a micro-intrusive GPU online energy optimization framework for iterative applications.
We also implement ODPP [1] as a comparison.

[1] P. Zou, L. Ang, K. Barker, and R. Ge, “Indicator-directed dynamic power management for iterative workloads on gpu-accelerated systems,” in 2020 20th IEEE/ACM International Symposium on Cluster, Cloud and Internet Computing (CCGRID). IEEE, 2020, pp. 559-568.

1. ./EPOpt contains source code of the GPOEO and ODPP [1].

1. ./PerformanceMeasurement (PerfMeasure) is a NVIDIA GPU measurer for energy/power/utilities/clocks

## Make GPOEO
Modify pathes of headers and libraries in ./EPOpt/makefile .
cd ./EPOpt && mkdir ./build && cp makefile ./build
cd ./build && make

## Make PerfMeasure
Modify pathes of headers and libraries in ./PerformanceMeasurement/makefile .
cd ./PerformanceMeasurement && mkdir ./build && cp makefile ./build
cd ./build && make

## Use GPOEO in python applications
GPOEO only has two APIs: 
```
Begin(GPUID4CUDA, GPUID4NVML, RunMode, MeasureOutDir, ModelDir, TestPrefix)
End()
```
GPUID4CUDA: GPU ID used in CUDA environment.
GPUID4NVML: GPU ID queried with nvidia-smi and used to initialize CUPTI.
RunMode: "WORK" (run energy saving online); "MEASURE" (measure hardware performance counter metrics and other data for training multi-objective prediction models).
MeasureOutDir: measurement output file path.
ModelDir: the path of multi-objective prediction models.
TestPrefix: prefix name of one run.

The two APIs should be inserted at the beginning and end of the main python file respectively.
As shown below:
```
from PyEPOpt import EPOpt

if __name__=="__main__":
    EPOpt.Begin(GPUID4CUDA, GPUID4NVML, RunMode, MeasureOutDir, ModelDir, TestPrefix)

    .....

    EPOpt.End()
```

## Use ODPP [1] in python applications
ODPP can be implemented as a daemon. However, for the convenience of comparing GPOEO and ODPP, we also implement ODPP into the same form: two APIs.
```
ODPPBegin(GPUID4CUDA, GPUID4NVML, RunMode, MeasureOutDir, ModelDir, TestPrefix)
ODPPEnd()
```
GPUID4CUDA: GPU ID used in CUDA environment.
GPUID4NVML: GPU ID queried with nvidia-smi and used to initialize CUPTI.
RunMode: "ODPP" (run ODPP online).
MeasureOutDir: not used.
ModelDir: the path of ODPP models.
TestPrefix: prefix name of one run.

The two APIs should be inserted at the beginning and end of the main python file respectively.
As shown below:
```
from ODPP import ODPPBegin, ODPPEnd

if __name__=="__main__":
    ODPPBegin(GPUID4CUDA, GPUID4NVML, RunMode, MeasureOutDir, ModelDir, TestPrefix)

    .....

    ODPPEnd()
```