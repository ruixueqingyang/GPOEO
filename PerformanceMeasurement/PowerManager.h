/*******************************************************************************
Copyright(C), 2020-2020, 瑞雪轻飏
     FileName: PowerManager.h
       Author: 瑞雪轻飏
      Version: 0.01
Creation Date: 20200506
  Description: 1. 包含各种头文件
               2. 定义 可用的频率对
       Others: //其他内容说明
*******************************************************************************/

#ifndef __POWER_MANAGER_H
#define __POWER_MANAGER_H

#include <stdio.h>
#include <stdlib.h>
#include <iostream>
#include <vector>
#include <system_error>
#include <string.h>
#include <string.h>
#include <vector>
#include <assert.h>
#include <math.h>
#include <fstream>

#include <pthread.h>
#include <unistd.h>
#include <getopt.h>
#include <nvml.h>
#include <signal.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <sys/time.h>
#include <signal.h>
#include <semaphore.h>
#include <mutex>
#include <thread>

#include <cuda.h>
#include <cuda_runtime.h>

#include "EPOptNVML.h"

// #define K40M "Tesla K40m"
#define RTX2080TI "NVIDIA GeForce RTX 2080 Ti"
#define RTX3080TI "NVIDIA GeForce RTX 3080 Ti"

struct GPU_CLK{
    unsigned int MemClk;
    unsigned int SMClk;
};

class POWER_MANAGER{
public:

    EPOPT_NVML* pMyNVML; // wfr 20210719 为了实现 NVML 不使用时被关闭, 同时保证 有任意线程使用时 不被关闭
    std::string GPUName; // -g GPU 型号
    int TuneType; // -t 调节类型: "DVFS" 0 DVFS; "POWER" 1 功率上限调节; "SM_RANGE" 2 核心频率调节
    // -i GPU 序号
    // int DeviceIDCUDADrv; // 初始化 CUDA Driver 用的 设备ID
    int DeviceIDNVML; // 初始化 CUDA NVML 用的 设备ID
    int indexClockPair; // -p F-F 对的 index
    int SMClkGearCount; // 频率 档位 的数量
    unsigned int memClockMHz;
    unsigned int graphicsClockMHz;
    unsigned int powerLimit; // -p W
    nvmlReturn_t nvmlResult;
    nvmlDevice_t device;
    unsigned int MinSMClk;
    unsigned int MaxSMClk;
    unsigned int BaseSMClk;
    unsigned int SMClkStep;
    // unsigned int ResetMinSMClk;
    // unsigned int ResetMaxSMClk;
    float LowerPct;
    float UpperPct;

    int TuneArg; // 临时保存调节参数, 初始化时使用

    bool isNVMLInit;

    const int* pGPUClkNum;
    const int* pGPUMaxPower;
    const struct GPU_CLK* pGPUClk;

    // pthread_t StrategyTID;
    // pthread_attr_t attr;
    // std::thread* ptrStrategy;
    // std::thread threadStrategy;

    int init(EPOPT_NVML* inpNVML){
        TuneType = -1;
        DeviceIDNVML = 1; // 初始化 CUDA NVML 用的 设备ID
        indexClockPair = -1;
        SMClkGearCount = -1;
        powerLimit = 0;
        TuneArg = -1;
        isNVMLInit = false;

        LowerPct = 0.0;
        UpperPct = 1.0;

        pGPUClkNum = NULL;
        pGPUMaxPower = NULL;
        pGPUClk = NULL;

        // ptrStrategy = NULL;

        pMyNVML = inpNVML;

        return 0;
    }

    int initArg(EPOPT_NVML* inpNVML);
    int initArg(int inDeviceIDNVML, EPOPT_NVML* inpNVML, int inTuneType, int inTuneArg);
    int initArg(int inDeviceIDNVML, EPOPT_NVML* inpNVML, int inTuneType, float inLowerPct, float inUpperPct);
    int initCLI(EPOPT_NVML* inpNVML, int argc, char** argv);
    
    POWER_MANAGER(EPOPT_NVML* inpNVML, int argc, char** argv){
        initCLI(inpNVML, argc, argv);
    }
    POWER_MANAGER(EPOPT_NVML* inpNVML = nullptr){
        init(inpNVML);
    }
    ~POWER_MANAGER(){
    }

    int GetSMClkGearCount();
    int GetBaseSMClk();
    int GetMinSMClk();
    int GetSMClkStep();
    std::string GetGPUName();

    int SetSMClkGear(int inSMClkGear);
    int SetSMClkRange(float inLowerPct, float inUpperPct);
    int SetSMClkRange(int inLowerSMClk, int inUpperSMClk);
    int ResetSMClkRange();

    int GetMemClkGearCount();
    int SetMemClkRange(float inLowerPct, float inUpperPct);
    int SetMemClkRange(int inLowerSMClk, int inUpperSMClk);
    int ResetMemClkRange();

    int Reset();

};

#endif