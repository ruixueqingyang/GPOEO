/*******************************************************************************
Copyright(C), 2020-2021, 瑞雪轻飏
     FileName: EPOptAPI.h
       Author: 瑞雪轻飏
      Version: 0.01
Creation Date: 20210315
  Description: 1. 包含各种头文件
               2. 定义 可用的频率对
       Others: //其他内容说明
*******************************************************************************/

#ifndef __ENERGY_PERFORMANCE_OPTIMIZER_API_H
#define __ENERGY_PERFORMANCE_OPTIMIZER_API_H

// #include <nvml.h>
// #include <cuda.h>
// #include <cuda_runtime.h>
// #include <cupti.h>
// #include <cupti_target.h>
// #include <cupti_profiler_target.h>
// #include <nvperf_host.h>
// #include <nvperf_target.h>
// #include <nvperf_cuda_host.h>
// #include <cuda.h>
#include <sys/types.h>
#include <unistd.h>
#include <stdio.h>
#include "iostream"
#include "vector"
#include <typeinfo>
// #include <time.h>
#include <sys/time.h>
#include <thread>
#include <Python.h>
#include <stdlib.h>
#include <system_error>
#include <getopt.h>
#include <sys/socket.h>
#include <netinet/in.h>


enum RUN_MODE { WORK = 0, LEARN, LEARN_WORK, MEASURE };

#define BUFF_LEN 128
#define SERVER_PORT 7777

// int EPOptBegin(int DeviceIDCUDADrv, int DeviceIDNVML, RUN_MODE RunModeID, std::string MeasureOutDir, std::string QTableDir, std::string TestName);
int EPOptBegin(int& argc, char** argv);

int EPOptEnd();

int SetSMClkRange(float LowerPercent, float UpperPercent);
int TimeStamp(std::string Description);
int StartMeasurement();
int StopMeasurement();
int ExitMeasurement();
int ResetMeasurement();
int ResetMeasurement(std::string OutPath);

#endif