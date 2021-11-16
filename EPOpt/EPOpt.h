/*******************************************************************************
Copyright(C), 2020-2020, 瑞雪轻飏
     FileName: EPOpt.h
       Author: 瑞雪轻飏
      Version: 0.01
Creation Date: 20200728
  Description: 1. 包含各种头文件
               2. 定义 可用的频率对
       Others: //其他内容说明
*******************************************************************************/

#ifndef __ENERGY_PERFORMANCE_OPTIMIZER_H
#define __ENERGY_PERFORMANCE_OPTIMIZER_H

#include <stdio.h>
#include <stdlib.h>
#include <iostream>
#include <vector>
#include <system_error>
#include <string.h>
#include <assert.h>
#include <math.h>
#include <fstream>
#include <map>

#include <pthread.h>
#include <unistd.h>
#include <getopt.h>
#include <signal.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <sys/time.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <signal.h>
#include <semaphore.h>
#include <mutex>
#include <thread>
#include <sys/ipc.h>
#include <sys/shm.h>

#include <cupti_target.h>
#include <cupti_profiler_target.h>
#include <nvperf_host.h>
#include "Metric.h"
#include "List.h"
#include "Eval.h"


#include "PowerManager.h"
#include "PowerMeasure.h"
// #define K40M "Tesla K40m"
// #define RTX2080TI "GeForce RTX 2080 Ti"
// #define DATA_BUFFER_COUNT 2
// kernel 一次运行 能同时测量的特征数量上限制
#define NUM_METRICS_PER_MEASURE 16
// 信息收集线程 向 测量线程该端口 发送 开始测量信号
#define UDP_PORT_MEASURE 5555
// 测量线程该端口 向 信息收集线程 发送 测量数据
#define UDP_PORT_DATA 6666
#define UDP_BUF_LEN_DATA 4096
#define UDP_BUF_LEN_SIGNAL 2048
#define SHARED_BUF_LEN 32000

#define FTOK_DIR "."
#define FTOK_ID_TIME 22
#define FTOK_ID_ENERGY 33
#define FTOK_ID_SMUTIL 44
#define FTOK_ID_MEMUTIL 55

#define MANAGER_STOP "MANAGER_STOP"
#define IS_CUDA_CONTEXT_VALID "IS_CUDA_CONTEXT_VALID"
#define METRIC_NAME_MSG "METRIC"

enum DATA_STATE {
    MEASURING, // 正在测量中，即测量线程正在占用
    USING, // 正在使用中，即频率调节算法正在占用
    UNUSED,// 该组数据被测量完，但还没被频率调节算法使用
    USED, // 频率调节算法已经使用完该组数据
    UNINIT // 未初始化
};

// ENG_PERF_MEASURER 的测量模式: 定时器中断结束测量, 信号触发结束测量
enum MEASURE_MODE { TIMER = 0, SIGNAL };

// EPOpt 系统的运行模式：工作， 学习， 学习工作, 仅测量
enum RUN_MODE { WORK = 0, LEARN, LEARN_WORK, MEASURE, ODPP, VOID };
// ENG_PERF_MEASURER 的测量模式：定时器周期性测量，信号触发测量
// enum MEASURE_MODE { TIMER = 0, REGION, SIGNAL };
enum MEASURE_BEGIN_SIGNAL{
    FEATURE_TRACE = 0,
    FEATURE,
    SIMPLE_FEATURE_TRACE,
    SIMPLE_FEATURE,
    // SIMPLE = 0,
    // FULL
    NONE
};

// enum CUPTI_STATE { RUNNING = 0, FINALIZING, FINALIZED };

class ENG_PERF_MANAGER{
public:
    bool isCUDAContextValid; // CUDA context is valid or not
    bool RunState; // 表示是否继续测量
    RUN_MODE RunMode;
    int DeviceIDNVML;
    CUdevice cuDevice;
    std::string chipName;
    EPOPT_NVML MyNVML;
    POWER_MANAGER PowerManager;
    MEASURE_MODE MeasureMode;

    pthread_t TID;
    pthread_attr_t attr;

    pthread_cond_t condGetData; // 控制启动一次数据读取
    pthread_mutex_t mutexGetData; // mutex for condMeasure
    pthread_cond_t condIsCuContextValid; // wfr 20210407
    pthread_mutex_t mutexIsCuContextValid; // wfr 20210407

    std::map< std::string, double > mapMetricNameValue;
    // std::map< std::string, double > tmpMapMetricNameValue;
    std::vector<float> vecPowerTrace;
    std::vector<int> vecSMUtilTrace;
    std::vector<int> vecMemUtilTrace;

    // UDP
    int measurer2manager_fd;
    int manager2measurer_fd;
    struct sockaddr_in measurer_addr;
    socklen_t SizeofMeasurerAddr;
    struct sockaddr_in manager_addr;
    socklen_t SizeofManagerAddr;

    // 共享内存初始化参数
    int shmIDTime, shmIDPower, shmIDSMUtil, shmIDMemUtil;
    int ret;
    key_t keyTime, keyPower, keySMUtil, keyMemUtil;
    double* pShmTime;
    float* pShmPower;
    int* pShmSMUtil;
    int* pShmMemUtil;
    unsigned long long shmTimeLen, shmPowerLen, shmSMUtilLen, shmMemUtilLen;
    unsigned long long SharedBufLen;
    pthread_mutex_t lockShm; // 共享内存读写锁

    // 获得 时间/能耗/性能 数据
    int ReceiveDataFromUDP();
    // wfr 20201221 启动测量, 如果是定时器模式则等待接收数据完成
    int StartMeasure(std::vector<std::string> vecMetricName, std::string MeasureBeginSignal, MEASURE_MODE inMeasureMode = MEASURE_MODE::SIGNAL, float MeasureDuration = 0);
    // wfr 20201221 信号模式下: 发送 结束测量信号, 结束测量并等待接收数据完成
    int StopMeasure();
    // wfr 20201221 信号模式下: 发送 获得数据信号, 等待接收数据完成
    int ReceiveData();
    std::map< std::string, double > GetFeature();
    std::vector< float > GetPowerTrace();
    std::vector< int > GetSMUtilTrace();
    std::vector< int > GetMemUtilTrace();
    int GetCurrGPUUtil();
    int GetCurrSMClk();
    int GetCurrMemClk();
    float GetPowerLimit();
    int NVMLInit();
    int NVMLUninit();

    int Init();
    int Init(int inDeviceIDNVML, RUN_MODE inRunMode, MEASURE_MODE inMeasureMode);
    int Stop(); // 停止测量

    ENG_PERF_MANAGER(){
        Init();
    }
    ~ENG_PERF_MANAGER();
};


class ENG_PERF_MEASURER{
public:
    bool RunState; // 表示是否继续测量
    bool isMeasuring; // is measuring or not
    bool isMeasurePower;
    bool isMeasurePerformace;
    int DeviceIDCUDADrv;
    int DeviceIDNVML;
    float MeasureDuration; // (s)
    RUN_MODE RunMode;
    MEASURE_MODE MeasureMode;
    MEASURE_BEGIN_SIGNAL MeasureBeginSignal;
    bool isMeasureFullFeature;
    bool isRecordTrace;
    bool isThreadInit;

    EPOPT_NVML MyNVML;
    CUdevice cuDevice;
    CUcontext cuContext;
    CUcontext cuContextOld;
    std::string chipName;
    std::vector<std::string> vecMetricName;

    std::vector<uint8_t> counterDataImagePrefix;
    std::vector<uint8_t> configImage;
    std::vector<uint8_t> counterDataImage;
    std::vector<uint8_t> counterDataScratchBuffer;
    std::vector<NV::Metric::Eval::MetricNameValue> metricNameValueMap;

    pthread_t TIDMeasure;
    pthread_attr_t AttrMeasure;

    pthread_t TIDCUContext;
    pthread_attr_t AttrCUContext;

    // pthread_cond_t condWaitThreadInit; // 控制启动一次测量的信号量
    // pthread_mutex_t mutexWaitThreadInit; // mutex for condMeasure
    pthread_mutex_t mutexSampling; // wfr 20210407 mutex for sampling, function BeginOnce() and EndOnce() mutex with each other
    pthread_mutex_t mutexCUDAContext; // wfr 20210407 mutex for cuContext
    pthread_mutex_t mutexCUPTI; // wfr 20210715 mutex for CUPTI
    pthread_cond_t condCUPTI; // wfr 20210715 cond for CUPTI

    std::vector<std::pair<std::string, double>> vecMetricNameValueMap;

    std::map< std::string, double > mapMetricNameValue;
    // std::map< std::string, double > tmpMapMetricNameValue;

    int CUPTIUsageCount;
    CUpti_Profiler_BeginSession_Params beginSessionParams;
    CUpti_Profiler_SetConfig_Params setConfigParams;
    CUpti_Profiler_EnableProfiling_Params enableProfilingParams;
    CUpti_Profiler_DisableProfiling_Params disableProfilingParams;
    CUpti_Profiler_PushRange_Params pushRangeParams;
    CUpti_Profiler_PopRange_Params popRangeParams;

    CUpti_Profiler_BeginPass_Params beginPassParams;
    CUpti_Profiler_EndPass_Params endPassParams;

    CUpti_Profiler_FlushCounterData_Params flushCounterDataParams;
    CUpti_Profiler_UnsetConfig_Params unsetConfigParams;
    CUpti_Profiler_EndSession_Params endSessionParams;

    // UDP
    int measurer2manager_fd;
    int manager2measurer_fd;
    struct sockaddr_in measurer_addr;
    socklen_t SizeofMeasurerAddr;
    struct sockaddr_in manager_addr;
    socklen_t SizeofManagerAddr;

    // 共享内存初始化参数
    int shmIDTime, shmIDPower, shmIDSMUtil, shmIDMemUtil;
    int ret;
    key_t keyTime, keyPower, keySMUtil, keyMemUtil;
    double* pShmTime;
    float* pShmPower;
    int* pShmSMUtil;
    int* pShmMemUtil;
    unsigned long long shmTimeLen, shmPowerLen, shmSMUtilLen, shmMemUtilLen;
    unsigned long long SharedBufLen;
    pthread_mutex_t lockShm; // 共享内存读写锁

    // initialization
    int Init();
    int Init(int inDeviceIDCUDADrv, int inDeviceIDNVML, RUN_MODE inRunMode, MEASURE_MODE inMeasureMode, std::vector<std::string> inVecMetricName, float inMeasureDuration = 0, bool inIsMeasurePower = true, bool inIsMeasurePerformace = true);
    ENG_PERF_MEASURER();
    ~ENG_PERF_MEASURER();
    int SendCUDAContextValidState(); // wfr 20210408 send cuda context valid state to manager process
    int SendStopSignal2Manager(); // wfr 20210409 send stop signal to manager
    int BeginOnce();
    // int EndOnce();
    int EndOnce(bool isCuContextValid = true);

    // wfr 20210408 set CUDA context, after context is created, and before context is destroyed
    int SetCUDAContext(CUcontext inCuContext);
    // 处理 UDP 发来的 开始测量 / 获取数据 等信号
    int HandleSignal();
    // 向 频率调节 python进程 启动的 信息收集 C++子线程 发送 能耗/时间/性能特征 数据
    int SendData(bool isTrace);
    int Stop(); // 停止测量

    // 下边几个配合使用，仅用来测量 metric
    int InitInCode(int inDeviceIDCUDADrv, int inDeviceIDNVML, RUN_MODE inRunMode, std::vector<std::string> inVecMetricName, bool inIsMeasurePower = true, bool inIsMeasurePerformace = true);
    int BeginInCode(); // 仅仅用来测量需要插入源代码中
    int EndInCode();
    int EndInCode(std::map<std::string, double>& inMapMetricNameValue); // 仅仅用来测量需要插入源代码中
};

#endif