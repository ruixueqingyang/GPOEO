/*******************************************************************************
Copyright(C), 2020-2020, 瑞雪轻飏
     FileName: PowerMeasure.h
       Author: 瑞雪轻飏
      Version: 0.01
Creation Date: 20200804
  Description: 1. 能耗测量
       Others: //其他内容说明
*******************************************************************************/

#ifndef __POWER_MEASURE_H
#define __POWER_MEASURE_H

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
// #define RTX2080TI "NVIDIA GeForce RTX 2080 Ti"
// #define RTX3080TI "NVIDIA GeForce RTX 3080 Ti"

// RTX2080TI
// #define POWER_THRESHOLD 1.65
// RTX3080TI
#define POWER_THRESHOLD 30
#define SAMPLE_INTERVAL 100
#define VECTOR_RESERVE 32000

void sleepbyselect(struct timeval tv);

typedef struct SampleData
{
    double TimeStamp; // (s)
    float Power; // (J)
} SAMPLE_DATA;

class POWER_MEASURE{
public:

    int DeviceID;
    std::string OutFilePath;
    std::ofstream outStream;

    float SampleInterval; // (ms) Sampling Interval
    float PowerThreshold; // (W) Part of power above this threshold is consider as dynamic power consumed by applications

    std::string GPUName; // GPU 型号
    nvmlReturn_t nvmlResult;
    bool isNVMLInit;
    EPOPT_NVML* pMyNVML; // wfr 20210719 为了实现 NVML 不使用时被关闭, 同时保证 有任意线程使用时 不被关闭

    // 这里是测量过程中的状态，用来管理测量过程：启动，停止等
    bool isFisrtSample;
    CUdevice cuDevice;
    nvmlDevice_t nvmlDevice;
    // int ComputeCapablityMajor;
    // int ComputeCapablityMinor;
    int isMeasuring; // 采样启动计数，每遇到一个启动请求++，每遇到一个停止请求--，到0才能停止
    bool isRecordTrace; // 是否记录 功率 trace

    // unsigned long long NumSampleMax;
    unsigned long long SampleCount;
    double ActualDuration; // (s) 实际采样区间长度

    struct timeval prevTimeStamp, currTimeStamp;
    double StartTimeStamp; // (s)
    float prevPower, currPower; // (W)
    int prevSMUtil, currSMUtil; // SM 占用率
    int prevMemUtil, currMemUtil; // Mem 占用率
    std::vector<double> vecTimeStamp;
    std::vector<double> vecTimeStampCpy;
    std::vector<float> vecPower;
    std::vector<float> vecPowerCpy;
    std::vector<int> vecSMUtil;
    std::vector<int> vecSMUtilCpy;
    std::vector<int> vecMemUtil;
    std::vector<int> vecMemUtilCpy;
    

    pthread_mutex_t lockData; // 为 vecTimeStampCpy/vecPowerCpy/vecSMUtilCpy/vecMemUtilCpy 加锁

    float minPower, maxPower; // (W, W)
    float avgPower, avgPowerAT, avgSMUtil, avgMemUtil; // (W) 阈值以上的功率
    float EnergyAT, Energy, sumSMUtil, sumMemUtil; // (J)


    int Init(EPOPT_NVML* inpNVML);
    int Init(int inDeviceID, EPOPT_NVML* inpNVML, std::string inOutFilePath="", bool inIsRecordTrace = true, float inSampleInterval = SAMPLE_INTERVAL, float inPowerThreshold = POWER_THRESHOLD);

    int Reset();
    int Begin(bool inIsRecordTrace = true);
    int End();

    POWER_MEASURE(EPOPT_NVML* inpNVML = nullptr);
    POWER_MEASURE(int inDeviceID, EPOPT_NVML* inpNVML, std::string inOutFilePath="", bool inIsRecordTrace = true, float inSampleInterval = SAMPLE_INTERVAL, float inPowerThreshold = POWER_THRESHOLD);
    ~POWER_MEASURE();
};

extern POWER_MEASURE PowerMeasurer;

static void Sampler(int signum);

#endif