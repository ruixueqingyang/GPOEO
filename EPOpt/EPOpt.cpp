/*******************************************************************************
Copyright(C), 2020-2020, 瑞雪轻飏
     FileName: EPOpt.cpp
       Author: 瑞雪轻飏
      Version: 0.01
Creation Date: 20200728
  Description: profile energy/power and performance data
               optimize energy-performance jointly
       Others: 
*******************************************************************************/

#include "EPOpt.h"
#include "CheckError.h"
#include "FileOp.h"
#include <nvml.h>
#include <cuda.h>
#include <cuda_runtime.h>
#include <cupti.h>
#include <cupti_target.h>
#include <cupti_profiler_target.h>
#include <nvperf_host.h>
#include <nvperf_target.h>
#include <nvperf_cuda_host.h>

#include <typeinfo>

// 用该函数启动测量进程，测量 能耗/时间/性能特征
static void* MeasureMetric(void* MeasurerThreadArgv);

// 用该函数启动数据收集线程，接收 UDP发来的 能耗/时间/性能特征
static void* threadReceiveData(void* ManagerThreadArgv);

bool CreateCounterDataImage(
    std::vector<uint8_t>& counterDataImage,
    std::vector<uint8_t>& counterDataScratchBuffer,
    std::vector<uint8_t>& counterDataImagePrefix);

const int maxNumRanges = 1;
const int maxRangesPerPass = maxNumRanges;
const int maxLaunchesPerPass = maxNumRanges;
const int minNestingLevel = 1;
const int numNestingLevels = 1;
const int maxNumRangeTreeNodes = maxNumRanges;
const int maxRangeNameLength = 64;

void* MeasurerThreadArgv[8];
void* ManagerThreadArgv[8];

const int MetricCount = 2;
const std::string MetricNameList[MetricCount] = {
    // "sm__inst_executed.avg.per_cycle_active", // ipc
    "sm__inst_issued.avg.per_cycle_active", // issued ipc
    "sm__average_inst_executed_pipe_alu_per_warp.pct", // ALU 指令占比
    // "sm__average_inst_executed_pipe_alu_per_warp.ratio", // ALU 指令占比


    // "sm__inst_executed_pipe_fp64.avg.pct_of_peak_sustained_active", // double_precision_fu_utilization
    // "sm__pipe_fma_cycles_active.avg.pct_of_peak_sustained_active", // single_precision_fu_utilization
    // "sm__inst_executed_pipe_fma.avg.pct_of_peak_sustained_active", //
    // "sm__inst_executed_pipe_fp16.avg.pct_of_peak_sustained_active", // half_precision_fu_utilization
    // "sm__inst_executed_pipe_xu.avg.pct_of_peak_sustained_active", // special_fu_utilization
    // "sm__pipe_tensor_cycles_active.avg.pct_of_peak_sustained_active", // tensor_precision_fu_utilization
};

int ENG_PERF_MANAGER::Init(){

    isCUDAContextValid = false;
    DeviceIDNVML = -1;

    pthread_cond_init(&condGetData, NULL);
    pthread_mutex_init(&mutexGetData, NULL);
    pthread_mutex_unlock(&mutexGetData);

    pthread_cond_init(&condIsCuContextValid, NULL);
    pthread_mutex_init(&mutexIsCuContextValid, NULL);
    pthread_mutex_unlock(&mutexIsCuContextValid);

    mapMetricNameValue.clear();
    vecPowerTrace.clear();

    // measurer ---> manager(current)

    // 初始化 UDP
    measurer2manager_fd = socket(AF_INET, SOCK_DGRAM, 0);
    if(measurer2manager_fd < 0){
        std::cout << "WARNING: create socket fail!\n" << std::endl;
        return -1;
    }

    memset(&manager_addr, 0, sizeof(manager_addr));
    manager_addr.sin_family = AF_INET;
    //manager_addr.sin_addr.s_addr = inet_addr(SERVER_IP);
    manager_addr.sin_addr.s_addr = htonl(INADDR_ANY);  //注意网络序转换
    manager_addr.sin_port = htons(UDP_PORT_DATA);  //注意网络序转换
    SizeofManagerAddr = sizeof(manager_addr);

    int err = bind(measurer2manager_fd, (struct sockaddr*)&manager_addr, SizeofManagerAddr);
    if(err < 0)
    {
        std::cout << "ENG_PERF_MANAGER ERROR: socket bind fail! (err_code = " << err << ")" << std::endl;
        return -1;
    }

/*
    // 初始化 TCP
    if( (measurer2manager_fd = socket(AF_INET,SOCK_STREAM,0)) == -1) {
        printf(" create socket error: %s (errno :%d)\n",strerror(errno),errno);
        return 0;
    }
    // 先把地址清空，检测任意IP
    memset(&manager_addr,0,sizeof(manager_addr));
    manager_addr.sin_family = AF_INET;
    manager_addr.sin_addr.s_addr = htonl(INADDR_ANY);
    manager_addr.sin_port = htons(UDP_PORT_DATA);
    //地址绑定到listenfd
    if ( bind(measurer2manager_fd, (struct sockaddr*)&manager_addr, sizeof(manager_addr)) == -1) {
        printf(" bind socket error: %s (errno :%d)\n",strerror(errno),errno);
        return 0;
    }
    //监听listenfd
    if( listen(manager_addr,10) == -1) {
        printf(" listen socket error: %s (errno :%d)\n",strerror(errno),errno);
        return 0;
    }
*/


    // measurer <--- manager(current)
    manager2measurer_fd = socket(AF_INET, SOCK_DGRAM, 0); //AF_INET:IPV4;SOCK_DGRAM:UDP
    if(manager2measurer_fd < 0)
    {
        printf("ENG_PERF_MANAGER ERROR: create socket fail!\n");
        return -1;
    }

    memset(&measurer_addr, 0, sizeof(measurer_addr));
    measurer_addr.sin_family = AF_INET;
    measurer_addr.sin_addr.s_addr = htonl(INADDR_ANY); //IP地址，需要进行网络序转换，INADDR_ANY：本地地址
    measurer_addr.sin_port = htons(UDP_PORT_MEASURE);  //端口号，需要网络序转换
    SizeofMeasurerAddr = sizeof(measurer_addr);

    // 初始化进程间共享内存
    // 创建key值
    keyTime = ftok(FTOK_DIR, FTOK_ID_TIME);
    if(keyTime == -1){
        perror("ENG_PERF_MANAGER: ftok: Time");
    }
    keyPower = ftok(FTOK_DIR, FTOK_ID_ENERGY);
    if(keyPower == -1){
        perror("ENG_PERF_MANAGER: ftok: Energy");
    }

    // wfr 20201221 初始化 共享内存读写锁
    pthread_mutex_init(&lockShm, NULL);
    pthread_mutex_unlock(&lockShm);

    return 0;
}

int ENG_PERF_MANAGER::Init(int inDeviceIDNVML, MEASURE_MODE inMeasureMode){
    DeviceIDNVML = inDeviceIDNVML;

    std::cout << "ENG_PERF_MANAGER: inDeviceIDNVML = " << inDeviceIDNVML << std::endl;

    PowerManager.initArg(DeviceIDNVML, &MyNVML, 2, 0.0, 1.0);
    MeasureMode = inMeasureMode;
    // std::cout << "PowerManager.initArg()" << std::endl;
    RunState = true;

    // 在这里启动新线程
    pthread_attr_init(&attr);
    pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);

    ManagerThreadArgv[0] = (void*)(this);
    // ManagerThreadArgv[1] = (void*)(&cuContext);

    // int MsgLen = 0;
    // int MsgIndex = 0;
    // char Msg[UDP_BUF_LEN_DATA];
    // memset(Msg, 0, UDP_BUF_LEN_DATA);
    
    // struct sockaddr_in tmpAddr;
    // unsigned int tmpSizeofAddr = sizeof(tmpAddr);
    // std::cout << "ENG_PERF_MANAGER::Init: manager is waiting the start signal" << std::endl;
    
    // MsgLen = recvfrom(measurer2manager_fd, Msg, UDP_BUF_LEN_DATA, 0, (struct sockaddr*)&tmpAddr, &tmpSizeofAddr);  //recvfrom是拥塞函数，没有数据就一直拥塞
    // if (0 == strncmp(MANAGER_START_STR, Msg, strlen(MANAGER_START_STR)))
    // {
    //     std::cout << "ENG_PERF_MANAGER::Init: manager has received the start signal" << std::endl;
    // }else
    // {
    //     std::cout << "ENG_PERF_MANAGER::Init ERROR: wrong manager start signal = " << Msg << std::endl;
    //     return -1;
    // }
        
    int err = pthread_create(&TID, &attr, threadReceiveData, (void*)ManagerThreadArgv);
    if(err != 0) {
        std::cerr << "ENG_PERF_MANAGER ERROR: pthread_create() return code: " << err << std::endl;
        exit(1);
    }

    return 0;
}

int ENG_PERF_MANAGER::Stop(){
    pthread_mutex_lock(&mutexIsCuContextValid);
    RunState = false;
    pthread_cond_broadcast(&condIsCuContextValid);
    pthread_mutex_unlock(&mutexIsCuContextValid);
    std::cout << "ENG_PERF_MANAGER::Stop" << std::endl;
    return 0;
}

ENG_PERF_MANAGER::~ENG_PERF_MANAGER(){

    // std::cout << "ENG_PERF_MANAGER::~ENG_PERF_MANAGER(): 0" << std::endl;
    close(manager2measurer_fd);
    close(measurer2manager_fd);
    std::cout << "ENG_PERF_MANAGER::~ENG_PERF_MANAGER(): 1" << std::endl;
}

// 用该函数启动数据收集线程，接收 UDP发来的 能耗/时间/性能特征
static void* threadReceiveData(void* ManagerThreadArgv){
    std::cout << "ENG_PERF_MANAGER: ReceiveData(): 进入" << std::endl;

    ENG_PERF_MANAGER& EPManager = *( ( (ENG_PERF_MANAGER**)ManagerThreadArgv )[0] );

    while (EPManager.RunState == true)
    {
        EPManager.ReceiveDataFromUDP();
    }

    pthread_exit(NULL);
}

int ENG_PERF_MANAGER::ReceiveDataFromUDP(){
    int MsgLen = 0;
    int MsgIndex = 0;
    char Msg[UDP_BUF_LEN_DATA];
    memset(Msg, 0, UDP_BUF_LEN_DATA);
    
    // std::cout << "ReceiveDataFromUDP in" << std::endl;

    // 先接收 测量完成信息:
    struct sockaddr_in tmpAddr;
    unsigned int tmpSizeofAddr = sizeof(tmpAddr);
    // std::cout << "ENG_PERF_MANAGER ReceiveDataFromUDP: recvfrom() ......." << std::endl;
    MsgLen = recvfrom(measurer2manager_fd, Msg, UDP_BUF_LEN_DATA, 0, (struct sockaddr*)&tmpAddr, &tmpSizeofAddr);  //recvfrom是拥塞函数，没有数据就一直拥塞
    // std::cout << "ENG_PERF_MANAGER ReceiveDataFromUDP: recvfrom() complete" << std::endl;
    if(MsgLen == -1){
        std::cout << "ReceiveDataFromUDP WARNING: recieve data fail!" << std::endl;
        return 0;
    }else{
        // std::cout << "ReceiveDataFromUDP: UDP MsgLen = " << std::dec << MsgLen << std::endl;
        // std::cout << "ReceiveDataFromUDP: Msg[0-32] = ";
        // for (size_t i = 0; i < 32; i++)
        // {
        //     std::cout << Msg[i];
        // }
        // std::cout << std::endl;
    }

    if (0 == strncmp(IS_CUDA_CONTEXT_VALID, Msg, strlen(IS_CUDA_CONTEXT_VALID)))
    {
        pthread_mutex_lock(&mutexIsCuContextValid);
        isCUDAContextValid = (bool)(Msg[1+strlen(IS_CUDA_CONTEXT_VALID)]);
        pthread_cond_broadcast(&condIsCuContextValid);
        pthread_mutex_unlock(&mutexIsCuContextValid);

        std::cout << "ReceiveDataFromUDP: isCUDAContextValid = " << isCUDAContextValid << std::endl;
        return 0;
    }else if(0 == strncmp(MANAGER_STOP, Msg, strlen(MANAGER_STOP))){

        // std::cout << "ReceiveDataFromUDP: get stop signal from measurer" << std::endl;

        pthread_mutex_lock(&mutexGetData);
        RunState = false;
        pthread_cond_broadcast(&condGetData);
        pthread_mutex_unlock(&mutexGetData);

        pthread_mutex_lock(&mutexIsCuContextValid);
        pthread_cond_broadcast(&condIsCuContextValid);
        pthread_mutex_unlock(&mutexIsCuContextValid);

        return 0;
    }
    
    mapMetricNameValue.clear();
    vecPowerTrace.clear();

    // 1. 获得 feature
    // 2. 获得 SampleCount, 等于 0 则说明没有测量 trace
    std::string tmpStr;
    double tmpData;
    unsigned long long tmpSampleCount = 0;
    while (MsgIndex<MsgLen)
    {
        tmpStr = &Msg[MsgIndex];
        MsgIndex += tmpStr.size() + 1;
        if (tmpStr != "SampleCount")
        {
            tmpData = *( (double*)(&Msg[MsgIndex]) );
            MsgIndex += sizeof(double);
            mapMetricNameValue.insert(std::pair<std::string, double>(tmpStr, tmpData));
        }else
        {
            tmpSampleCount = *( (unsigned long long*)(&Msg[MsgIndex]) );
            MsgIndex += sizeof(unsigned long long);
        }
    }
    std::cout << "ReceiveDataFromUDP: mapMetricNameValue.size() = " << mapMetricNameValue.size() << std::endl;
    // std::cout << "ReceiveDataFromUDP: tmpSampleCount = " << tmpSampleCount << std::endl;

    // 然后从 共享内存读取数据
    if (tmpSampleCount > 0)
    {
        // 加锁 共享内存读写
        pthread_mutex_lock(&lockShm);

        // 初始化进程间共享内存
        // 创建key值
        keyTime = ftok(FTOK_DIR, FTOK_ID_TIME);
        if(keyTime == -1){
            perror("ReceiveData: ftok: Time");
        }
        keyPower = ftok(FTOK_DIR, FTOK_ID_ENERGY);
        if(keyPower == -1){
            perror("ReceiveData: ftok: Energy");
        }
    
        // 创建进程间共享内存
        shmTimeLen = tmpSampleCount * sizeof(double);
        shmIDTime = shmget(keyTime, shmTimeLen, IPC_CREAT|0666);
        if(shmIDTime < 0){
            perror("ReceiveData: shmget: Time");
            exit(-1);
        }
        shmPowerLen = tmpSampleCount * sizeof(float);
        shmIDPower = shmget(keyPower, shmPowerLen, IPC_CREAT|0666);
        if(shmIDPower < 0){
            perror("ReceiveData: shmget: Energy");
            exit(-1);
        }
    
        // 映射进程间共享内存
        pShmTime = (double*)shmat(shmIDTime, NULL, 0);
        if(pShmTime < 0){
            perror("ReceiveData: shmat: Time");
            _exit(-1);
        }
        pShmPower = (float*)shmat(shmIDPower, NULL, 0);
        if(pShmPower < 0){
            perror("ReceiveData: shmat: Energy");
            _exit(-1);
        }

        vecPowerTrace.insert(vecPowerTrace.begin(), pShmPower, pShmPower+tmpSampleCount);

        // 解锁 共享内存读写
        pthread_mutex_unlock(&lockShm);

        // std::cout << "ReceiveDataFromUDP: tmpSampleCount = " << tmpSampleCount << std::endl;
        // std::cout << "ReceiveDataFromUDP: vecPowerTrace.size() = " << vecPowerTrace.size() << std::endl;

        // 分离共享内存和当前进程
        ret = shmdt(pShmTime);
        if(ret < 0)
        {
            perror("ReceiveData: shmdt: Time");
            exit(1);
        }
        ret = shmdt(pShmPower);
        if(ret < 0)
        {
            perror("ReceiveData: shmdt: Energy");
            exit(1);
        }
    }

    // std::cout << "ReceiveDataFromUDP: has got data" << std::endl;
    pthread_mutex_lock(&mutexGetData);
    // std::cout << "ReceiveDataFromUDP: 获得信号量锁" << std::endl;
    pthread_cond_broadcast(&condGetData);
    // std::cout << "ReceiveDataFromUDP: 发送信号量" << std::endl;
    pthread_mutex_unlock(&mutexGetData);
    // std::cout << "ReceiveDataFromUDP: 释放信号量锁" << std::endl;
    // std::cout << "ReceiveDataFromUDP: has sent condGetData" << std::endl;

    // std::cout << "ENG_PERF_MANAGER: ReceiveDataFromUDP(): 退出" << std::endl;
    return 0;
}

// 获得 时间/能耗/性能 数据
std::map< std::string, double > ENG_PERF_MANAGER::GetFeature(){
    return mapMetricNameValue;
}
// 获得 功率 trace 数据
std::vector< float > ENG_PERF_MANAGER::GetTrace(){
    return vecPowerTrace;
}

int ENG_PERF_MANAGER::GetCurrGPUUtil(){

    nvmlReturn_t nvmlResult;
    nvmlDevice_t nvmlDevice;

    MyNVML.Init();
    nvmlResult = nvmlDeviceGetHandleByIndex(DeviceIDNVML, &nvmlDevice);
	if (NVML_SUCCESS != nvmlResult)
	{
		printf("ENG_PERF_MANAGER::GetCurrGPUUtil: Failed to get handle for device %d: %s\n", DeviceIDNVML, nvmlErrorString(nvmlResult));
		return 101;
	}

    nvmlUtilization_t currUtil;
    nvmlResult = nvmlDeviceGetUtilizationRates(nvmlDevice, &currUtil);
    if (NVML_SUCCESS != nvmlResult) {
        printf("ENG_PERF_MANAGER::GetCurrGPUUtil: Failed to get utilization rate: %s\n", nvmlErrorString(nvmlResult));
        return 101;
    }

    int CurrGPUUtil = currUtil.gpu;

    MyNVML.Uninit();

    return CurrGPUUtil;
}

int ENG_PERF_MANAGER::GetCurrSMClk(){

    nvmlReturn_t nvmlResult;
    nvmlDevice_t nvmlDevice;

    MyNVML.Init();
    nvmlResult = nvmlDeviceGetHandleByIndex(DeviceIDNVML, &nvmlDevice);
	if (NVML_SUCCESS != nvmlResult)
	{
		printf("ENG_PERF_MANAGER::GetCurrGPUUtil: Failed to get handle for device %d: %s\n", DeviceIDNVML, nvmlErrorString(nvmlResult));
		return 101;
	}

    nvmlUtilization_t currUtil;
    unsigned int currSMClk; // (MHz)
    nvmlResult = nvmlDeviceGetClockInfo(nvmlDevice, NVML_CLOCK_SM, &currSMClk);
    if (NVML_SUCCESS != nvmlResult) {
        printf("ENG_PERF_MANAGER::GetCurrSMClk: Failed to get SM clock: %s\n", nvmlErrorString(nvmlResult));
        return 1365;
    }

    MyNVML.Uninit();

    return currSMClk;
}

int ENG_PERF_MANAGER::NVMLInit(){
    MyNVML.Init();
    return 0;
}

int ENG_PERF_MANAGER::NVMLUninit(){
    MyNVML.Uninit();
    return 0;
}

// wfr 20201221 启动测量, 如果是定时器模式则等待接收数据完成
int ENG_PERF_MANAGER::StartMeasure(std::vector<std::string> vecMetricName, std::string MeasureBeginSignal, MEASURE_MODE inMeasureMode, float MeasureDuration){

    // pthread_mutex_lock(&mutexGetData);
    // mapMetricNameValue.clear();
    // vecPowerTrace.clear();
    // pthread_mutex_unlock(&mutexGetData);

    pthread_mutex_lock(&mutexIsCuContextValid);
    while (isCUDAContextValid == false && RunState == true)
    {
        std::cout << "ENG_PERF_MANAGER::StartMeasure: waiting CUDA context valid" << std::endl;
        pthread_cond_wait(&condIsCuContextValid, &mutexIsCuContextValid);
    }
    pthread_mutex_unlock(&mutexIsCuContextValid);

    std::cout << "ENG_PERF_MANAGER::StartMeasure: isCUDAContextValid = " << isCUDAContextValid << std::endl;

    if (RunState == false)
    {
        return 0;
    }
    
    MeasureMode = inMeasureMode;

    unsigned int Len = UDP_BUF_LEN_DATA;
    unsigned int LenSend = 0;
    char buf[Len];
    unsigned int count = 0;
    
    strncpy(buf, MeasureBeginSignal.c_str(), MeasureBeginSignal.size()+1);
    LenSend += MeasureBeginSignal.size()+1;
    
    *(int*)(&buf[LenSend]) = (int)MeasureMode;
    LenSend += sizeof(int);

    *(float*)(&buf[LenSend]) = (float)MeasureDuration;
    LenSend += sizeof(float);

    // wfr 20210619 可以在这里向 measurer 发送 Metric Name, 来指定本次测量的 Metric
    // 例如: "METRIC\03METRIC_NAME_0\0METRIC_NAME_1\0METRIC_NAME_2"
    if (vecMetricName.size()>0)
    {
        strncpy(&buf[LenSend], METRIC_NAME_MSG, strlen(METRIC_NAME_MSG)+1);
        LenSend += strlen(METRIC_NAME_MSG)+1;
        *(int*)(&buf[LenSend]) = (int)vecMetricName.size();
        LenSend += sizeof(int);

        for (size_t i = 0; i < vecMetricName.size(); i++)
        {
            strncpy(&buf[LenSend], vecMetricName[i].c_str(), vecMetricName[i].size()+1);
            LenSend += vecMetricName[i].size()+1;
        }
        
    }
    
    // wfr 20210701 for debug
    // int tmpIndex = 0;
    // std::cout << "ENG_PERF_MANAGER::StartMeasure: buf: ";
    // std::cout << &buf[tmpIndex] << " ";
    // tmpIndex += strlen(&buf[tmpIndex]) + 1;
    // std::cout << *(int*)&buf[tmpIndex] << " ";
    // tmpIndex += sizeof(int);
    // std::cout << *(float*)&buf[tmpIndex] << " ";
    // tmpIndex += sizeof(float);
    // std::cout << &buf[tmpIndex] << " ";
    // tmpIndex += strlen(&buf[tmpIndex]) + 1;
    // std::cout << *(int*)&buf[tmpIndex] << " ";
    // tmpIndex += sizeof(int);
    // for (size_t i = 0; i < (int)vecMetricName.size(); i++)
    // {
    //     std::cout << &buf[tmpIndex] << " ";
    //     tmpIndex += strlen(&buf[tmpIndex]) + 1;
    // }
    // std::cout << std::endl;
    

    // 发送开始测量信号
    sendto(manager2measurer_fd, buf, LenSend, 0, (struct sockaddr*)&measurer_addr, SizeofMeasurerAddr);
    // std::cout << "ENG_PERF_MANAGER::StartMeasure: 已发送开始测量信号, MeasureBeginSignal = " << MeasureBeginSignal << ", MeasureMode = " << MeasureMode << ", MeasureDuration = " << MeasureDuration << std::endl;

    if (MeasureMode == MEASURE_MODE::TIMER)
    {
        // 等待测量完成
        pthread_mutex_lock(&mutexGetData);
        if (isCUDAContextValid == true && RunState == true)
        {
            pthread_cond_wait(&condGetData, &mutexGetData);
        }
        pthread_mutex_unlock(&mutexGetData);
    }

    return 0;
}

// wfr 20201221 信号模式下: 发送 结束测量信号, 结束测量并等待接收数据完成
int ENG_PERF_MANAGER::StopMeasure(){

    // if (RunState == false)
    // {
    //     return 0;
    // }

    unsigned int Len = UDP_BUF_LEN_SIGNAL;
    unsigned int LenSend = 0;
    char buf[Len];
    strcpy(buf, "STOP");
    LenSend = strlen("STOP") + 1;

    // 发送结束测量信号
    sendto(manager2measurer_fd, buf, LenSend, 0, (struct sockaddr*)&measurer_addr, SizeofMeasurerAddr);

    // 等待获得数据完成
    std::cout << "ENG_PERF_MANAGER::StopMeasure: wait get data" << std::endl;
    pthread_mutex_lock(&mutexGetData);
    if (isCUDAContextValid == true && RunState == true)
    {
        pthread_cond_wait(&condGetData, &mutexGetData);
    }
    pthread_mutex_unlock(&mutexGetData);
    std::cout << "ENG_PERF_MANAGER::StopMeasure: wait get data complete" << std::endl;

    return 0;
}

// wfr 20201221 信号模式下: 发送 获得数据信号, 等待接收数据完成
int ENG_PERF_MANAGER::ReceiveData(){

    // if (RunState == false)
    // {
    //     return 0;
    // }

    unsigned int Len = UDP_BUF_LEN_SIGNAL;
    unsigned int LenSend = 0;
    char buf[Len];
    strcpy(buf, "GET_DATA");
    LenSend = strlen("GET_DATA") + 1;

    // 发送获得数据信号
    sendto(manager2measurer_fd, buf, LenSend, 0, (struct sockaddr*)&measurer_addr, SizeofMeasurerAddr);

    // 等待获得数据完成
    pthread_mutex_lock(&mutexGetData);
    if (isCUDAContextValid == true && RunState == true)
    {
        pthread_cond_wait(&condGetData, &mutexGetData);
    }
    pthread_mutex_unlock(&mutexGetData);

    return 0;
}

// initialization
int ENG_PERF_MEASURER::Init(){
    std::cout << "ENG_PERF_MEASURER::Init()" << std::endl;
    DeviceIDCUDADrv = -1;
    DeviceIDNVML = -1;
    MeasureBeginSignal = MEASURE_BEGIN_SIGNAL::FEATURE_TRACE;
    isMeasuring = false;
    isMeasureFullFeature = true;
    isRecordTrace = false;
    isThreadInit = false;
    cuContext = NULL;
    cuContextOld = cuContext;
    CUPTIUsageCount = 0;

    // pthread_cond_init(&condWaitThreadInit, NULL);
    // pthread_mutex_init(&mutexWaitThreadInit, NULL);
    // pthread_mutex_unlock(&mutexWaitThreadInit);

    pthread_mutex_init(&mutexCUDAContext, NULL);
    pthread_mutex_unlock(&mutexCUDAContext);

    pthread_mutex_init(&mutexCUPTI, NULL);
    pthread_mutex_unlock(&mutexCUPTI);
    pthread_cond_init(&condCUPTI, NULL);

    vecMetricName.clear();
    mapMetricNameValue.clear();

    // measurer(current) ---> manager
/*
    // 初始化 TCP
    //创建socket
    if( (measurer2manager_fd = socket(AF_INET,SOCK_STREAM,0)) == -1) {
        printf(" create socket error: %s (errno :%d)\n",strerror(errno),errno);
        return 0;
    }
    
    memset(&manager_addr,0,sizeof(manager_addr));
    manager_addr.sin_family = AF_INET;
    manager_addr.sin_addr.s_addr = htonl(INADDR_ANY);  //注意网络序转换
    manager_addr.sin_port = htons(UDP_PORT_DATA);
*/
    // 初始化 UDP
    measurer2manager_fd = socket(AF_INET, SOCK_DGRAM, 0);
    if(measurer2manager_fd < 0){
        std::cout << "WARNING: create socket fail!\n" << std::endl;
        return -1;
    }

    memset(&manager_addr, 0, sizeof(manager_addr));
    manager_addr.sin_family = AF_INET;
    //manager_addr.sin_addr.s_addr = inet_addr(SERVER_IP);
    manager_addr.sin_addr.s_addr = htonl(INADDR_ANY);  //注意网络序转换
    manager_addr.sin_port = htons(UDP_PORT_DATA);  //注意网络序转换
    SizeofManagerAddr = sizeof(manager_addr);


    // measurer(current) <--- manager
    manager2measurer_fd = socket(AF_INET, SOCK_DGRAM, 0); //AF_INET:IPV4;SOCK_DGRAM:UDP
    if(manager2measurer_fd < 0)
    {
        printf("ENG_PERF_MEASURER ERROR: create socket fail!\n");
        return -1;
    }

    memset(&measurer_addr, 0, sizeof(measurer_addr));
    measurer_addr.sin_family = AF_INET;
    measurer_addr.sin_addr.s_addr = htonl(INADDR_ANY); //IP地址，需要进行网络序转换，INADDR_ANY：本地地址
    measurer_addr.sin_port = htons(UDP_PORT_MEASURE);  //端口号，需要网络序转换
    SizeofMeasurerAddr = sizeof(measurer_addr);

    int err = bind(manager2measurer_fd, (struct sockaddr*)&measurer_addr, SizeofMeasurerAddr);
    if(err < 0)
    {
        std::cout << "ENG_PERF_MEASURER ERROR: socket bind fail! (err_code = " << err << ")" << std::endl;
        return -1;
    }

    // 创建key值, 供进程间共享内存创建过程使用
    keyTime = ftok(FTOK_DIR, FTOK_ID_TIME);
    if(keyTime == -1){
        perror("ENG_PERF_MEASURER: ftok: Time");
    }
    keyPower = ftok(FTOK_DIR, FTOK_ID_ENERGY);
    if(keyPower == -1){
        perror("ENG_PERF_MEASURER: ftok: Energy");
    }

    // 创建进程间共享内存
    shmTimeLen = SHARED_BUF_LEN * sizeof(double);
    shmIDTime = shmget(keyTime, shmTimeLen, IPC_CREAT|0666);    
    if(shmIDTime < 0){
        perror("ENG_PERF_MEASURER: shmget: Time");
        exit(-1);
    }
    shmPowerLen = SHARED_BUF_LEN * sizeof(float);
    shmIDPower = shmget(keyPower, shmPowerLen, IPC_CREAT|0666);    
    if(shmIDPower < 0){
        perror("ENG_PERF_MEASURER: shmget: Energy");
        exit(-1);
    }
    SharedBufLen = SHARED_BUF_LEN;

    // 映射进程间共享内存
    pShmTime = (double*)shmat(shmIDTime, NULL, 0);
    if(pShmTime < 0){
        perror("ENG_PERF_MEASURER: shmat: Time");
        _exit(-1);
    }
    pShmPower = (float*)shmat(shmIDPower, NULL, 0);
    if(pShmPower < 0){
        perror("ENG_PERF_MEASURER: shmat: Energy");
        _exit(-1);
    }

    // wfr 20201221 初始化 共享内存读写锁
    pthread_mutex_init(&lockShm, NULL);
    pthread_mutex_unlock(&lockShm);

    std::cout << "ENG_PERF_MEASURER::Init() complete" << std::endl;

    return 0;
}

// wfr 20210408
int ENG_PERF_MEASURER::SetCUDAContext(CUcontext inCuContext){
    // pthread_mutex_lock(&mutexCUDAContext);
    // std::cout << "ENG_PERF_MEASURER: mutexCUDAContext 0" << std::endl;
    cuContext = inCuContext;
    // pthread_mutex_unlock(&mutexCUDAContext);
    // std::cout << "ENG_PERF_MEASURER: mutexCUDAContext 1" << std::endl;

    return 0;
}

void EPMeasureCallbackHandler(void* userdata, CUpti_CallbackDomain domain, CUpti_CallbackId cbid, void* cbdata){
    
    ENG_PERF_MEASURER* pEPMeasurer = (ENG_PERF_MEASURER*)(userdata);
    const CUpti_CallbackData* cbInfo = (CUpti_CallbackData*)cbdata;

    if(domain == CUPTI_CB_DOMAIN_RESOURCE){

        // printf("EPMeasureCallbackHandler: cbid = %d\n", cbid);

        if(cbid == CUPTI_CBID_RESOURCE_CONTEXT_CREATED){

            printf("EPMeasureCallbackHandler: CUPTI_CBID_RESOURCE_CONTEXT_CREATED\n");
            CUcontext cuContext;
            // printf("cuCtxGetCurrent Begin\n");
            DRIVER_API_CALL(cuCtxGetCurrent(&cuContext));
            // printf("cuCtxGetCurrent End\n");
            std::cout << "EPMeasureCallbackHandler: cuContext = " << std::hex << (void*)cuContext << std::dec << std::endl;

            // wfr 20210408
            pthread_mutex_lock(&pEPMeasurer->mutexCUDAContext);
            // std::cout << "ENG_PERF_MEASURER: mutexCUDAContext 00" << std::endl;
            pEPMeasurer->SetCUDAContext(cuContext);
            pEPMeasurer->SendCUDAContextValidState();
            pthread_mutex_unlock(&pEPMeasurer->mutexCUDAContext);
            // std::cout << "ENG_PERF_MEASURER: mutexCUDAContext 01" << std::endl;

            // wfr 20210507 如果是测量模式, 在 cuda context 创建后 启动测量
            if (pEPMeasurer->RunMode == RUN_MODE::MEASURE)
            {   
                std::cout << "ENG_PERF_MEASURER: pEPMeasurer->BeginInCode()" << std::endl;
                pEPMeasurer->BeginInCode();
            }
            

        }else if(cbid == CUPTI_CBID_RESOURCE_CONTEXT_DESTROY_STARTING){

            printf("EPMeasureCallbackHandler: CUPTI_CBID_RESOURCE_CONTEXT_DESTROY_STARTING\n");

            // wfr 20210507 如果是测量模式, 在 cuda context 创建后 启动测量
            if (pEPMeasurer->RunMode == RUN_MODE::MEASURE)
            {   
                std::cout << "ENG_PERF_MEASURER: pEPMeasurer->EndInCode()" << std::endl;
                pEPMeasurer->EndInCode();
            }else{
                // wfr 20210408
                pEPMeasurer->EndOnce(false);
            }

            printf("EPMeasureCallbackHandler: 0\n");
            // pEPMeasurer->SetCUDAContext(0);
            // printf("EPMeasureCallbackHandler: 1\n");
            // pEPMeasurer->SendCUDAContextValidState();
            // printf("EPMeasureCallbackHandler: 2\n");
        }
        
    }

    pthread_mutex_lock(&pEPMeasurer->mutexCUPTI);
    pthread_cond_broadcast(&pEPMeasurer->condCUPTI);
    pthread_mutex_unlock(&pEPMeasurer->mutexCUPTI);
}

// wfr 20210715 create a thread to handle CUpti_CallbackFunc to catch cuContext
// once catch cuContext then cuptiFinalize() to avoid overhead
// CatchCUContext
static void* CatchCUContext(void* MeasurerThreadArgv){

    std::cout << "CatchCUContext: in" << std::endl;

    ENG_PERF_MEASURER* pEPMeasurer = ( (ENG_PERF_MEASURER**)MeasurerThreadArgv )[0];

    // wfr 20210715 reference count ++
    pthread_mutex_lock(&pEPMeasurer->mutexCUPTI);
    pEPMeasurer->CUPTIUsageCount++;
    std::cout << "CatchCUContext: CUPTIUsageCount++ = " << pEPMeasurer->CUPTIUsageCount << std::endl;

    CUpti_SubscriberHandle subscriber;
    CUPTI_API_CALL(cuptiSubscribe(&subscriber, (CUpti_CallbackFunc)EPMeasureCallbackHandler, (void*)pEPMeasurer));
    CUPTI_API_CALL(cuptiEnableCallback(1, subscriber, CUPTI_CB_DOMAIN_RESOURCE, CUPTI_CBID_RESOURCE_CONTEXT_CREATED));
    CUPTI_API_CALL(cuptiEnableCallback(1, subscriber, CUPTI_CB_DOMAIN_RESOURCE, CUPTI_CBID_RESOURCE_CONTEXT_DESTROY_STARTING));

    pEPMeasurer -> isThreadInit = true;
    pthread_cond_wait(&pEPMeasurer->condCUPTI, &pEPMeasurer->mutexCUPTI);
    pthread_mutex_unlock(&pEPMeasurer->mutexCUPTI);
    std::cout << "CatchCUContext: pEPMeasurer->cuContext = " << std::hex << 
    (void*)pEPMeasurer->cuContext << std::dec << std::endl;
    
    pthread_mutex_lock(&pEPMeasurer->mutexCUPTI);
    // wfr 20210715 reference count --
    // if (pEPMeasurer->CUPTIUsageCount > 0)
    // {
    //     ;
    // }
    
    pEPMeasurer->CUPTIUsageCount--;
    std::cout << "CatchCUContext: CUPTIUsageCount-- = " << pEPMeasurer->CUPTIUsageCount << std::endl;

    if (pEPMeasurer->CUPTIUsageCount == 0 && pEPMeasurer->RunMode != RUN_MODE::MEASURE)
    {
        // wfr 20210715 finalize CUPTI and clean up
        CUPTI_API_CALL(cuptiEnableCallback(0, subscriber, CUPTI_CB_DOMAIN_RESOURCE, CUPTI_CBID_RESOURCE_CONTEXT_CREATED));
        CUPTI_API_CALL(cuptiEnableCallback(0, subscriber, CUPTI_CB_DOMAIN_RESOURCE, CUPTI_CBID_RESOURCE_CONTEXT_DESTROY_STARTING));
        CUPTI_API_CALL(cuptiUnsubscribe(subscriber));
        CUPTI_API_CALL(cuptiActivityFlushAll(1));
        // CUPTI_API_CALL(cuptiFinalize());
        std::cout << "CatchCUContext: cuptiFinalize() complete" << std::endl;
    }

    pthread_mutex_unlock(&pEPMeasurer->mutexCUPTI);
    
    std::cout << "CatchCUContext: exit" << std::endl;
    pthread_exit(NULL);
}

int ENG_PERF_MEASURER::Init(int inDeviceIDCUDADrv, int inDeviceIDNVML, RUN_MODE inRunMode, MEASURE_MODE inMeasureMode, std::vector<std::string> inVecMetricName, float inMeasureDuration, bool inIsMeasurePower, bool inIsMeasurePerformace){

    // std::cout << "ENG_PERF_MEASURER::EPInit" << std::endl;
    //打印pid
    std::cout << "ENG_PERF_MEASURER::Init: PID = " << std::hex << getpid() << std::endl;
    //打印tid
    std::cout << "ENG_PERF_MEASURER::Init: TID = " << std::hex << std::this_thread::get_id() << std::endl;

    DeviceIDCUDADrv = inDeviceIDCUDADrv;
    DeviceIDNVML = inDeviceIDNVML;

    RunMode = inRunMode;
    MeasureMode = inMeasureMode;
    MeasureDuration = inMeasureDuration;
    isMeasurePower = inIsMeasurePower;
    isMeasurePerformace = inIsMeasurePerformace;
    vecMetricName = inVecMetricName;
    // std::cout << "DeviceIDCUDADrv = " << DeviceIDCUDADrv << std::endl;

    // std::cout << "cuInit" << std::endl;
    CHECK_CUDA_DRIVER_ERROR(cuInit(0)); // wfr 20210329 initialize CUDA driver
    // wfr 20210329 ENG_PERF_MEASURER::Init is called at the entry of applications, so CUDA driver should be initialized by itself

    int DeviceCount;
    // std::cout << "cuDeviceGetCount" << std::endl;
    CHECK_CUDA_DRIVER_ERROR(cuDeviceGetCount(&DeviceCount));
    std::cout << "ENG_PERF_MEASURER::Init: cuDeviceGetCount: DeviceCount = " << DeviceCount << std::endl;

    // std::cout << "cuDeviceGet" << std::endl;
    CHECK_CUDA_DRIVER_ERROR(cuDeviceGet(&cuDevice, DeviceIDCUDADrv));

    CUuuid uuid;
    // std::cout << "cuDeviceGetUuid" << std::endl;
    CHECK_CUDA_DRIVER_ERROR(cuDeviceGetUuid(&uuid, cuDevice));
    std::cout << "ENG_PERF_MEASURER::Init: uuid = " << std::hex;
    for(int i = 0; i<16; i++){
        std::cout << ((unsigned int)(uuid.bytes[i])&((unsigned int)(0xFF))) << " ";
    }
    std::cout << std::dec << std::endl;

    // std::cout << "cuCtxCreate" << std::endl;
    // CHECK_CUDA_DRIVER_ERROR(cuCtxCreate(&cuContext, 0, cuDevice));
    // std::cout << "cuCtxSynchronize" << std::endl;
    // CHECK_CUDA_DRIVER_ERROR(cuCtxSynchronize());

    // get current CUDA context for profiling
    // CHECK_CUDA_DRIVER_ERROR(cuCtxSynchronize());
    // std::cout << "cuCtxGetCurrent" << std::endl;
    // CHECK_CUDA_DRIVER_ERROR(cuCtxGetCurrent(&cuContext));
    // CHECK_CUDA_DRIVER_ERROR(cuCtxSynchronize());

    // if(cuContext == NULL){
    //     std::cout << "ENG_PERF_MEASURER ERROR: Cannot get current cuda context!" << std::endl;
    //     return -1;
    // }

    // std::cout << "ENG_PERF_MEASURER::Init: cuContext = " << std::hex << (void*)cuContext << std::dec << std::endl;

    if (isMeasurePower == true)
    {
        PowerMeasurer.Init(DeviceIDNVML, &MyNVML);
        // std::cout << "PowerMeasurer.Init()" << std::endl;
    }

    RunState = true;

    // 在这里启动测量线程
    pthread_attr_init(&AttrMeasure);
    pthread_attr_setdetachstate(&AttrMeasure, PTHREAD_CREATE_DETACHED);

    MeasurerThreadArgv[0] = (void*)(this);
    // MeasurerThreadArgv[1] = (void*)(&cuContext);

    int err = pthread_create(&TIDMeasure, &AttrMeasure, MeasureMetric, (void*)MeasurerThreadArgv);
    if(err != 0) {
        std::cerr << "ERROR: pthread_create() return code: " << err << std::endl;
        exit(1);
    }

    // 20210715 这里启动新线程，在其中调用 cupti 的 API 观察是否会导致显著开销
    pthread_attr_init(&AttrCUContext);
    pthread_attr_setdetachstate(&AttrCUContext, PTHREAD_CREATE_DETACHED);
    int tmpErr = pthread_create(&TIDCUContext, &AttrCUContext, CatchCUContext, (void*)MeasurerThreadArgv);
    if(err != 0) {
        std::cerr << "ERROR: pthread_create() return code: " << tmpErr << std::endl;
        exit(1);
    }

    // wfr 20210326 enable callback function EPMeasureCallbackHandler() for cuCtxCreate() to get cuContext and begin EPMeasurer
    // CUpti_SubscriberHandle subscriber;
    // CUPTI_API_CALL(cuptiSubscribe(&subscriber, (CUpti_CallbackFunc)EPMeasureCallbackHandler, (void*)this));
    // CUPTI_API_CALL(cuptiEnableCallback(1, subscriber, CUPTI_CB_DOMAIN_RESOURCE, CUPTI_CBID_RESOURCE_CONTEXT_CREATED));
    // CUPTI_API_CALL(cuptiEnableCallback(1, subscriber, CUPTI_CB_DOMAIN_RESOURCE, CUPTI_CBID_RESOURCE_CONTEXT_DESTROY_STARTING));
    // CUPTIUsageCount = 1;

    while (isThreadInit != true)
    {
        usleep(50*1000); // 50 ms
    }
    
    return 0;
}

// wfr 20210408
int ENG_PERF_MEASURER::SendCUDAContextValidState(){

    // pthread_mutex_lock(&mutexCUDAContext);
    // std::cout << "ENG_PERF_MEASURER: mutexCUDAContext 2" << std::endl;

    unsigned int Len = UDP_BUF_LEN_SIGNAL;
    unsigned int LenSend = 0;
    char buf[Len];
    memset(buf, 0, UDP_BUF_LEN_SIGNAL);

    strcpy(buf, IS_CUDA_CONTEXT_VALID);
    LenSend += 1 + strlen(IS_CUDA_CONTEXT_VALID);

    bool CUDAContextValidState = (cuContext != 0);
    buf[LenSend] = (char)CUDAContextValidState;
    LenSend += 1;

    // wfr 20210329 send start signal to manager, manager should be started after measurer
    if(connect(measurer2manager_fd,(struct sockaddr*)&manager_addr,sizeof(manager_addr)) < 0) {
        printf(" connect socket error: %s(errno :%d)\n",strerror(errno),errno);
        return 0;
    }
    sleep(2);
    sendto(measurer2manager_fd, buf, LenSend, 0, (struct sockaddr*)&manager_addr, SizeofManagerAddr);

    std::cout << "ENG_PERF_MEASURER::SendCUDAContextValidState: CUDAContextValidState = " << CUDAContextValidState << std::endl;

    // pthread_mutex_unlock(&mutexCUDAContext);
    // std::cout << "ENG_PERF_MEASURER: mutexCUDAContext 3" << std::endl;

    return 0;
}

int ENG_PERF_MEASURER::SendStopSignal2Manager(){

    unsigned int Len = UDP_BUF_LEN_SIGNAL;
    unsigned int LenSend = 0;
    char buf[Len];
    memset(buf, 0, UDP_BUF_LEN_SIGNAL);

    strcpy(buf, MANAGER_STOP);
    LenSend += 1 + strlen(MANAGER_STOP);

    // wfr 20210329 send stop signal to manager
    if(connect(measurer2manager_fd,(struct sockaddr*)&manager_addr,sizeof(manager_addr)) < 0) {
        printf(" connect socket error: %s(errno :%d)\n",strerror(errno),errno);
        return 0;
    }
    sendto(measurer2manager_fd, buf, LenSend, 0, (struct sockaddr*)&manager_addr, SizeofManagerAddr);

    std::cout << "ENG_PERF_MEASURER::SendStopSignal2Manager: send stop signal to manager" << std::endl;

    return 0;
}

int ENG_PERF_MEASURER::Stop(){
    std::cout << "ENG_PERF_MEASURER::Stop: PID = " << std::hex << getpid() << std::endl;
    //打印tid
    std::cout << "ENG_PERF_MEASURER::Stop: TID = " << std::hex << std::this_thread::get_id() << std::endl;

    RunState = false;
    return 0;
}

// 用该函数启动测量 thread，测量 能耗/时间/性能特征
static void* MeasureMetric(void* MeasurerThreadArgv){
    bool isContinue = true;
    ENG_PERF_MEASURER& EPMeasurer = *( ( (ENG_PERF_MEASURER**)MeasurerThreadArgv )[0] );

    std::cout << "MeasureMetric: PID = " << std::hex << getpid() << std::endl;
    //打印tid
    std::cout << "MeasureMetric: TID = " << std::hex << std::this_thread::get_id() << std::endl;

    // std::cout << "开始获取 cuContext" << std::endl;

    // std::cout << "MeasureMetric: cuContext = " << std::hex << (void*)(EPMeasurer.cuContext) << std::dec << std::endl;

    // DRIVER_API_CALL(cuInit(0));
    // DRIVER_API_CALL(cuCtxPushCurrent(cuContext));
    // DRIVER_API_CALL(cuCtxSetCurrent(EPMeasurer.cuContext));

    NVPW_InitializeHost_Params initializeHostParams = { NVPW_InitializeHost_Params_STRUCT_SIZE };
    NVPW_API_CALL(NVPW_InitializeHost(&initializeHostParams));

    while (EPMeasurer.RunState == true) {

        // std::cout << "MeasureMetric: 0" << std::endl;
        EPMeasurer.HandleSignal();
        // std::cout << "MeasureMetric: 1" << std::endl;
        // std::cout << "\nENG_PERF_MEASURER::Begin" << std::endl;
        EPMeasurer.BeginOnce();
        // std::cout << "MeasureMetric: 2" << std::endl;

        if (EPMeasurer.MeasureMode == MEASURE_MODE::TIMER)
        {
            struct timeval TimeStamp0, TimeStamp1;

            // 延时
            unsigned int tmpDuration = (unsigned int)(EPMeasurer.MeasureDuration*1000*1000);

            struct timeval tv;
            tv.tv_sec = (unsigned int)(tmpDuration / 1000000);
            tv.tv_usec = (unsigned int)(tmpDuration % 1000000);

            // std::cout << "usleep(" << tmpDuration << ")" << std::endl;
            // gettimeofday(&TimeStamp0, NULL);
            sleepbyselect(tv);
            // usleep(tmpDuration);
            // gettimeofday(&TimeStamp1, NULL);
            // std::cout << "usleep(" << tmpDuration << ") completes" << std::endl;

            // double tmpActualDuration = (TimeStamp1.tv_sec - TimeStamp0.tv_sec) + (TimeStamp1.tv_usec - TimeStamp0.tv_usec) * 1e-6;
            // std::cout << "MeasureMetric: tmpActualDuration = " << tmpActualDuration << std::endl;
        }else if (EPMeasurer.MeasureMode == MEASURE_MODE::SIGNAL)
        {
            // std::cout << "MeasureMetric: 3" << std::endl;
            EPMeasurer.HandleSignal();
            // std::cout << "MeasureMetric: 4" << std::endl;
        }

        // std::cout << "MeasureMetric: 5" << std::endl;
        EPMeasurer.EndOnce(true);
        // std::cout << "MeasureMetric: 6" << std::endl;
        // std::cout << "EPMeasurer.EndOnce()\n" << std::endl;

        // 判断是否继续测量
        if (isContinue == false)
        {
            break;
        }
    }

    std::cout << "MeasureMetric: stop measure" << std::endl;
    pthread_exit(NULL);
}

int ENG_PERF_MEASURER::BeginOnce(){
    // std::cout << "ENG_PERF_MEASURER::BeginOnce: in" << std::endl;

    pthread_mutex_lock(&mutexCUDAContext);
    // std::cout << "ENG_PERF_MEASURER: mutexCUDAContext 4" << std::endl;
    if (isMeasuring == true)
    {
        std::cout << "ENG_PERF_MEASURER::BeginOnce WARNING: cuContext = " << std::hex << cuContext << std::endl;
        std::cout << "ENG_PERF_MEASURER::BeginOnce WARNING: isMeasuring = " << isMeasuring << std::endl;
        pthread_mutex_unlock(&mutexCUDAContext);
        // std::cout << "ENG_PERF_MEASURER: mutexCUDAContext 5" << std::endl;
        return 0;
    }
    
    if (cuContext != cuContextOld)
    {
        DRIVER_API_CALL(cuCtxSetCurrent(cuContext));
        cuContextOld = cuContext;
        std::cout << "ENG_PERF_MEASURER::BeginOnce: set current cuContext = " << std::hex << cuContext << std::dec << std::endl;
    }    

    int MetricIndex = -1;

    // 1. 确定本次需要收集的 metric 的 index
    MetricIndex = 0;
    // std::cout << "ENG_PERF_MEASURER::BeginOnce: MetricIndex = 0" << std::endl;
    mapMetricNameValue.clear();
    mapMetricNameValue.insert({ {"Energy", (double)0.0}, {"Time", (double)0.0} });

    
    // 2. 收集 metric
    // 3. 平均能耗和运行时间
    std::vector<std::string> subVecMetricName;
    // subVecMetricName.reserve(NUM_METRICS_PER_MEASURE);
    // if ( MetricIndex+NUM_METRICS_PER_MEASURE < vecMetricName.size() )
    // {
    //     subVecMetricName.assign(vecMetricName.begin()+MetricIndex, vecMetricName.begin()+MetricIndex+NUM_METRICS_PER_MEASURE);
    // }else{
    //     subVecMetricName.assign(vecMetricName.begin()+MetricIndex, vecMetricName.end());
    // }

    subVecMetricName = vecMetricName;


    // for (size_t i = 0; i < vecMetricName.size(); i++)
    // {
    //     std::cout << "vecMetricName[" << i << "] = " << vecMetricName[i] << std::endl;
    // }
    // for (size_t i = 0; i < subVecMetricName.size(); i++)
    // {
    //     std::cout << "subVecMetricName[" << i << "] = " << subVecMetricName[i] << std::endl;
    // }
    
    // wfr 20210408 verify cuda context valid or not and send signal to manager
    if (cuContext != 0)
    {
        unsigned int version;
        CUresult tmpErr = cuCtxGetApiVersion(cuContext, &version);
        if (tmpErr != 0)
        {
            std::cout << "ENG_PERF_MEASURER::BeginOnce 0 WARNING: cuda context invalid" << std::endl;
            cuContext = 0;
            SendCUDAContextValidState();
        }
    }

    // std::cout << "ENG_PERF_MEASURER::BeginOnce: 0" << std::endl;
    std::cout << "ENG_PERF_MEASURER::BeginOnce: current cuContext = " << std::hex << cuContext << std::dec << std::endl;
    
    if (cuContext != 0 && isMeasurePerformace==true && isMeasureFullFeature==true)
    {

        pthread_mutex_lock(&mutexCUPTI);
        CUPTIUsageCount++;
        std::cout << "ENG_PERF_MEASURER::BeginOnce: CUPTIUsageCount++ = " << CUPTIUsageCount << std::endl;
        pthread_mutex_unlock(&mutexCUPTI);

        // CUcontext cuContext;
        // DRIVER_API_CALL(cuCtxGetCurrent(&cuContext));
        // std::cout << "ENG_PERF_MEASURER::BeginOnce: cuContext = " << std::hex << (void*)cuContext << std::dec << std::endl;

        // CPUTI 初始化
        CUpti_Profiler_Initialize_Params profilerInitializeParams = {CUpti_Profiler_Initialize_Params_STRUCT_SIZE};
        CHECK_CUPTI_ERROR(cuptiProfilerInitialize(&profilerInitializeParams));
        /* Get chip name for the cuda  device */
        CUpti_Device_GetChipName_Params getChipNameParams = { CUpti_Device_GetChipName_Params_STRUCT_SIZE };
        getChipNameParams.deviceIndex = DeviceIDCUDADrv;
        CHECK_CUPTI_ERROR(cuptiDeviceGetChipName(&getChipNameParams));
        chipName = getChipNameParams.pChipName;

        /* Generate configuration for metrics, this can also be done offline */
        // NVPW_InitializeHost_Params initializeHostParams = { NVPW_InitializeHost_Params_STRUCT_SIZE };
        // CHECK_NVPW_ERROR(NVPW_InitializeHost(&initializeHostParams));

        beginSessionParams = {CUpti_Profiler_BeginSession_Params_STRUCT_SIZE};
        setConfigParams = {CUpti_Profiler_SetConfig_Params_STRUCT_SIZE};
        enableProfilingParams = {CUpti_Profiler_EnableProfiling_Params_STRUCT_SIZE};
        disableProfilingParams = {CUpti_Profiler_DisableProfiling_Params_STRUCT_SIZE};
        pushRangeParams = {CUpti_Profiler_PushRange_Params_STRUCT_SIZE};
        popRangeParams = {CUpti_Profiler_PopRange_Params_STRUCT_SIZE};

        counterDataImagePrefix.clear();
        configImage.clear();
        counterDataImage.clear();
        counterDataScratchBuffer.clear();
        metricNameValueMap.clear();
        // std::string CounterDataFileName("SimpleCupti.counterdata");
        // std::string CounterDataSBFileName("SimpleCupti.counterdataSB");

        // wfr 20201102 这里初始化输出数据结构
        if (subVecMetricName.size()) {
            if(!NV::Metric::Config::GetConfigImage(chipName, subVecMetricName, configImage)){
                std::cout << "Failed to create configImage" << std::endl;
                exit(-1);
            }
            if(!NV::Metric::Config::GetCounterDataPrefixImage(chipName, subVecMetricName, counterDataImagePrefix)){
                std::cout << "Failed to create counterDataImagePrefix" << std::endl;
                exit(-1);
            }
        }else{
            std::cout << "No metrics provided to profile" << std::endl;
            exit(-1);
        }
        if(!CreateCounterDataImage(counterDataImage, counterDataScratchBuffer, counterDataImagePrefix))
        {
            std::cout << "Failed to create counterDataImage" << std::endl;
            exit(-1);
        }

        // std::cout << "ENG_PERF_MEASURER::BeginOnce: 1" << std::endl;

        // CUPTI 开始测量
        CUpti_ProfilerReplayMode profilerReplayMode;
        CUpti_ProfilerRange profilerRange;
        // wfr 20201102 这里初始化测量模式
        profilerReplayMode = CUPTI_UserReplay; // CUPTI_UserReplay CUPTI_KernelReplay
        profilerRange = CUPTI_UserRange; // CUPTI_UserRange CUPTI_AutoRange

        beginSessionParams.ctx = NULL; // cuContext
        beginSessionParams.counterDataImageSize = counterDataImage.size();
        beginSessionParams.pCounterDataImage = &counterDataImage[0];
        beginSessionParams.counterDataScratchBufferSize = counterDataScratchBuffer.size();
        beginSessionParams.pCounterDataScratchBuffer = &counterDataScratchBuffer[0];
        beginSessionParams.range = profilerRange;
        beginSessionParams.replayMode = profilerReplayMode;
        beginSessionParams.maxRangesPerPass = maxRangesPerPass;
        beginSessionParams.maxLaunchesPerPass = maxLaunchesPerPass;
        
        // std::cout << "ENG_PERF_MEASURER::BeginOnce: 2" << std::endl;

        CHECK_CUPTI_ERROR(cuptiProfilerBeginSession(&beginSessionParams));

        setConfigParams.pConfig = &configImage[0];
        setConfigParams.configSize = configImage.size();
        setConfigParams.passIndex = 0;
        setConfigParams.minNestingLevel = minNestingLevel;
        setConfigParams.numNestingLevels = numNestingLevels;
        CHECK_CUPTI_ERROR(cuptiProfilerSetConfig(&setConfigParams));

        beginPassParams = {CUpti_Profiler_BeginPass_Params_STRUCT_SIZE};

        std::string rangeName = "userrangeA";
        pushRangeParams.pRangeName = rangeName.c_str();

        CHECK_CUPTI_ERROR(cuptiProfilerBeginPass(&beginPassParams));
        CHECK_CUPTI_ERROR(cuptiProfilerEnableProfiling(&enableProfilingParams));
        CHECK_CUPTI_ERROR(cuptiProfilerPushRange(&pushRangeParams));

        // std::cout << "ENG_PERF_MEASURER::BeginOnce: 3" << std::endl;
    }

    // std::cout << "ENG_PERF_MEASURER::BeginOnce: 4" << std::endl;

    if (isMeasurePower==true)
    {
        PowerMeasurer.Reset();
        PowerMeasurer.Begin(isRecordTrace);
        // std::cout << "PowerMeasurer.Begin(isRecordTrace)" << std::endl;
    }

    // std::cout << "ENG_PERF_MEASURER::BeginOnce: 5" << std::endl;

    isMeasuring = true;

    // CUPTI 只能测量完整的 kernel, 即测量时间区间刚开始和快结束时的不完整 kernel 不会被测量, 
    // 而能耗和时间的测量是确确实实持续整个测量时间区间的, 
    // 这样就导致 性能特征 和 能耗/时间 的测量不匹配 .........
    // ??? 这个问题需要解决, 
    // 一个可能的技术路线是, 查查 kernel 启动/结束 有没有给提供可用的钩子函数啥的
    // 在钩子函数中启动 能耗测量 并 打时间戳

    pthread_mutex_unlock(&mutexCUDAContext);
    // std::cout << "ENG_PERF_MEASURER: mutexCUDAContext 6" << std::endl;
    return 0;
}

// 等待 UDP 发来的 开始测量信号
int ENG_PERF_MEASURER::HandleSignal(){
    int MsgLen = 0;
    char Msg[UDP_BUF_LEN_SIGNAL];

    while (true)
    {
        memset(Msg, 0, UDP_BUF_LEN_SIGNAL);
        struct sockaddr_in tmpAddr;
        unsigned int tmpSizeofAddr = sizeof(tmpAddr);
        // std::cout << "HandleSignal: waiting UDP......" << std::endl;
        MsgLen = recvfrom(manager2measurer_fd, Msg, UDP_BUF_LEN_DATA, 0, (struct sockaddr*)&tmpAddr, &tmpSizeofAddr);  //recvfrom是拥塞函数，没有数据就一直拥塞
        if(MsgLen == -1){
            std::cout << "ENG_PERF_MEASURER::HandleSignal WARNING: recieve data fail!" << std::endl;
            continue;
        }else{
            // std::cout << "ENG_PERF_MEASURER::HandleSignal: MsgLen = " << MsgLen << std::endl;
            std::cout << "ENG_PERF_MEASURER::HandleSignal: Msg = " << Msg << std::endl;

            std::string tmpSignal(Msg);

            if (tmpSignal == "FEATURE_TRACE")
            {
                MeasureBeginSignal = MEASURE_BEGIN_SIGNAL::FEATURE_TRACE;
                isMeasureFullFeature = true;
                isRecordTrace = true;
                MeasureMode = (MEASURE_MODE)( *(int*)(&Msg[tmpSignal.size()+1]) );
                if (MeasureMode == MEASURE_MODE::TIMER)
                {
                    MeasureDuration = *(float*)(&Msg[tmpSignal.size()+1+sizeof(int)]);
                }
                // std::cout << "ENG_PERF_MEASURER::MeasureBeginSignal = FEATURE_TRACE" << std::endl;
                // return 0;
            }
            else if (tmpSignal == "FEATURE")
            {
                MeasureBeginSignal = MEASURE_BEGIN_SIGNAL::FEATURE;
                isMeasureFullFeature = true;
                isRecordTrace = false;
                MeasureMode = (MEASURE_MODE)( *(int*)(&Msg[tmpSignal.size()+1]) );
                if (MeasureMode == MEASURE_MODE::TIMER)
                {
                    MeasureDuration = *(float*)(&Msg[tmpSignal.size()+1+sizeof(int)]);
                }
                // std::cout << "ENG_PERF_MEASURER::MeasureBeginSignal = FEATURE" << std::endl;
                // return 0;
            }
            else if (tmpSignal == "SIMPLE_FEATURE_TRACE")
            {
                MeasureBeginSignal = MEASURE_BEGIN_SIGNAL::SIMPLE_FEATURE_TRACE;
                isMeasureFullFeature = false;
                isRecordTrace = true;
                MeasureMode = (MEASURE_MODE)( *(int*)(&Msg[tmpSignal.size()+1]) );
                if (MeasureMode == MEASURE_MODE::TIMER)
                {
                    MeasureDuration = *(float*)(&Msg[tmpSignal.size()+1+sizeof(int)]);
                }
                // std::cout << "ENG_PERF_MEASURER::MeasureBeginSignal = SIMPLE_FEATURE_TRACE" << std::endl;
                return 0;
            }
            else if (tmpSignal == "SIMPLE_FEATURE")
            {
                MeasureBeginSignal = MEASURE_BEGIN_SIGNAL::SIMPLE_FEATURE;
                isMeasureFullFeature = false;
                isRecordTrace = false;
                MeasureMode = (MEASURE_MODE)( *(int*)(&Msg[tmpSignal.size()+1]) );
                if (MeasureMode == MEASURE_MODE::TIMER)
                {
                    MeasureDuration = *(float*)(&Msg[tmpSignal.size()+1+sizeof(int)]);
                }
                // std::cout << "ENG_PERF_MEASURER::MeasureBeginSignal = SIMPLE_FEATURE" << std::endl;
                return 0;
            }
            else if (tmpSignal == "GET_DATA") // 获得能耗信息
            {
                std::cout << "ENG_PERF_MEASURER::HandleSignal: GET_DATA" << std::endl;
                SendData(true);
            }
            else if (tmpSignal == "STOP")
            {
                std::cout << "ENG_PERF_MEASURER::HandleSignal: STOP" << std::endl;
                return 0;
            }
            else
            {
                return 0;
            }

            if (tmpSignal == "FEATURE_TRACE" || tmpSignal == "FEATURE")
            {
                int tmpLen = tmpSignal.size() + 1 + sizeof(int) + sizeof(float);
                std::string tmpStr = &Msg[tmpLen];
                // std::cout << "ENG_PERF_MEASURER::HandleSignal: tmpStr = " << tmpStr << std::endl;
                tmpLen += tmpStr.size() + 1;
                // std::cout << "ENG_PERF_MEASURER::HandleSignal: tmpLen = " << tmpLen << std::endl;
                if (MsgLen>tmpLen && tmpStr==METRIC_NAME_MSG)
                {
                    int tmpCount = *(int*)(&Msg[tmpLen]);
                    // std::cout << "ENG_PERF_MEASURER::HandleSignal: tmpCount = " << tmpCount << std::endl;
                    tmpLen += sizeof(int);
                    if (tmpCount > 0)
                    {
                        vecMetricName.clear();
                        for (size_t i = 0; i < tmpCount; i++)
                        {   
                            tmpStr = &Msg[tmpLen];
                            tmpLen += tmpStr.size() + 1;
                            vecMetricName.emplace_back(tmpStr);
                            // std::cout << "ENG_PERF_MEASURER::HandleSignal: tmpStr = " << tmpStr << std::endl;
                        }
                    }
                }
                return 0;
            }

            continue;
        }
    }
    
    return 0;
}

// inserted after a code snippet to end profiling and optimization, used in pairs with BeginOnce()
int ENG_PERF_MEASURER::EndOnce(bool isCuContextValid){
    // std::cout << "ENG_PERF_MEASURER::EndOnce(): 0" << std::endl;

    pthread_mutex_lock(&mutexCUDAContext);
    // std::cout << "ENG_PERF_MEASURER::EndOnce(): 1" << std::endl;
    // std::cout << "ENG_PERF_MEASURER: mutexCUDAContext 7" << std::endl;
    if (isMeasuring == false)
    {
        std::cout << "ENG_PERF_MEASURER::EndOnce WARNING: cuContext = " << std::hex << cuContext << std::endl;
        std::cout << "ENG_PERF_MEASURER::EndOnce WARNING: isMeasuring = " << isMeasuring << std::endl;
        pthread_mutex_unlock(&mutexCUDAContext);
        // std::cout << "ENG_PERF_MEASURER: mutexCUDAContext 8" << std::endl;
        return 0;
    }
    // std::cout << "ENG_PERF_MEASURER::EndOnce(): 2" << std::endl;

    // std::cout << "ENG_PERF_MEASURER::EndOnce: isMeasurePower = " << isMeasurePower << std::endl;
    // std::cout << "ENG_PERF_MEASURER::EndOnce: isMeasurePerformace = " << isMeasurePerformace << std::endl;
    // std::cout << "ENG_PERF_MEASURER::EndOnce: isMeasureFullFeature = " << isMeasureFullFeature << std::endl;

    if (isMeasurePower==true)
    {
        PowerMeasurer.End();
    }

    // std::cout << "ENG_PERF_MEASURER::EndOnce(): 3" << std::endl;

    if (isCuContextValid == false)
    {
        cuContext = 0;
    }
    
    // wfr 20210408 verify cuda context valid or not and send signal to manager
    if (cuContext != 0)
    {
        unsigned int version;
        CUresult tmpErr = cuCtxGetApiVersion(cuContext, &version);
        if (tmpErr != 0)
        {
            std::cout << "ENG_PERF_MEASURER::EndOnce WARNING: cuda context invalid" << std::endl;
            cuContext = 0;
            // std::cout << "ENG_PERF_MEASURER::EndOnce(): 4" << std::endl;
        }
    }

    // std::cout << "ENG_PERF_MEASURER::EndOnce(): 5" << std::endl;

    if (cuContext == 0)
    {
        SendCUDAContextValidState();
    }

    // std::cout << "ENG_PERF_MEASURER::EndOnce(): 6" << std::endl;

    // std::cout << "ENG_PERF_MEASURER::EndOnce(): 6-0" << std::endl;
    if (cuContext != 0 && isMeasurePerformace==true && isMeasureFullFeature==true)
    {
        // CUcontext cuContextLocal;
        // DRIVER_API_CALL(cuCtxGetCurrent(&cuContextLocal));
        // std::cout << "ENG_PERF_MEASURER::EndOnce: cuContext = " << std::hex << (void*)cuContextLocal << std::dec << std::endl;

        CHECK_CUPTI_ERROR(cuptiProfilerPopRange(&popRangeParams));
        CHECK_CUPTI_ERROR(cuptiProfilerDisableProfiling(&disableProfilingParams));
        endPassParams = {CUpti_Profiler_EndPass_Params_STRUCT_SIZE};
        CHECK_CUPTI_ERROR(cuptiProfilerEndPass(&endPassParams));

        // std::cout << "ENG_PERF_MEASURER::EndOnce(): 6-1" << std::endl;

        flushCounterDataParams = {CUpti_Profiler_FlushCounterData_Params_STRUCT_SIZE};
        CHECK_CUPTI_ERROR(cuptiProfilerFlushCounterData(&flushCounterDataParams));
        unsetConfigParams = {CUpti_Profiler_UnsetConfig_Params_STRUCT_SIZE};
        CHECK_CUPTI_ERROR(cuptiProfilerUnsetConfig(&unsetConfigParams));
        endSessionParams = {CUpti_Profiler_EndSession_Params_STRUCT_SIZE};
        CHECK_CUPTI_ERROR(cuptiProfilerEndSession(&endSessionParams));

        // std::cout << "ENG_PERF_MEASURER::EndOnce(): 6-2" << std::endl;

        /* Evaluation of metrics collected in counterDataImage, this can also be done offline*/
        // std::cout << "ENG_PERF_MEASURER::EndOnce(): PrintMetricValues" << std::endl;
        // NV::Metric::Eval::PrintMetricValues(chipName, counterDataImage, vecMetricName);
        // std::cout << "ENG_PERF_MEASURER::EndOnce(): PrintMetricValues" << std::endl;
        NV::Metric::Eval::GetMetricGpuValue(chipName, counterDataImage, vecMetricName, metricNameValueMap);
        // std::cout << "ENG_PERF_MEASURER::EndOnce(): metricNameValueMap.size() = " << metricNameValueMap.size() << std::endl;

        // std::cout << "ENG_PERF_MEASURER::EndOnce(): 6-3" << std::endl;

        // DeInitialize CUPTI
        CUpti_Profiler_DeInitialize_Params profilerDeInitializeParams = {CUpti_Profiler_DeInitialize_Params_STRUCT_SIZE};
        CHECK_CUPTI_ERROR(cuptiProfilerDeInitialize(&profilerDeInitializeParams));

        // std::cout << "ENG_PERF_MEASURER::EndOnce(): 6-4" << std::endl;

        for(unsigned int i = 0; i<metricNameValueMap.size(); i++){
            double SumValue = 0.0;
            for (size_t j = 0; j < metricNameValueMap[i].rangeNameMetricValueMap.size(); j++)
            {
                SumValue += metricNameValueMap[i].rangeNameMetricValueMap[j].second;
            }

            // std::cout << "ENG_PERF_MEASURER::EndOnce(): 6-5" << std::endl;
            
            mapMetricNameValue.insert(std::pair<std::string, double>(metricNameValueMap[i].metricName, SumValue));
        }

        // wfr 20210715 finalize CUPTI and clean up
        // if (CUPTIUsageCount == 1)
        // {
        //     CUPTIUsageCount = 0;
        //     CUpti_SubscriberHandle subscriber;
        //     CUPTI_API_CALL(cuptiEnableCallback(0, subscriber, CUPTI_CB_DOMAIN_RESOURCE, CUPTI_CBID_RESOURCE_CONTEXT_CREATED));
        //     CUPTI_API_CALL(cuptiEnableCallback(0, subscriber, CUPTI_CB_DOMAIN_RESOURCE, CUPTI_CBID_RESOURCE_CONTEXT_DESTROY_STARTING));
        //     CUPTI_API_CALL(cuptiUnsubscribe(subscriber));
        //     std::cout << "ENG_PERF_MEASURER::EndOnce():cuptiUnsubscribe() complete" << std::endl;
        // }
        
        // CUPTI_API_CALL(cuptiActivityFlushAll(1));
        // CUPTI_API_CALL(cuptiFinalize());
        // std::cout << "ENG_PERF_MEASURER::EndOnce():　cuptiFinalize() complete" << std::endl;

        pthread_mutex_lock(&mutexCUPTI);
        CUPTIUsageCount--;
        std::cout << "ENG_PERF_MEASURER::BeginOnce: CUPTIUsageCount-- = " << CUPTIUsageCount << std::endl;
        if (CUPTIUsageCount == 0 && RunMode != RUN_MODE::MEASURE)
        {
            // wfr 20210715 finalize CUPTI and clean up
            CUPTI_API_CALL(cuptiActivityFlushAll(1));
            CUPTI_API_CALL(cuptiFinalize());
            std::cout << "ENG_PERF_MEASURER::EndOnce():　cuptiFinalize() complete" << std::endl;
        }
        pthread_mutex_unlock(&mutexCUPTI);
    }

    // std::cout << "ENG_PERF_MEASURER::EndOnce(): 7" << std::endl;

    // std::cout << "ENG_PERF_MEASURER::EndOnce(): isMeasurePower = " << isMeasurePower << std::endl;
    // std::cout << "ENG_PERF_MEASURER::EndOnce(): isMeasurePerformace = " << isMeasurePerformace << std::endl;

    if (isMeasurePower==true)
    {
        if (isMeasurePerformace==true)
        {
            mapMetricNameValue["Energy"] = PowerMeasurer.EnergyAT;
            mapMetricNameValue["Time"] = PowerMeasurer.ActualDuration;
        }else
        {
            mapMetricNameValue["Energy"] = PowerMeasurer.EnergyAT;
            mapMetricNameValue["Time"] = PowerMeasurer.ActualDuration;
            for (size_t i = 0; i < vecMetricName.size(); i++)
            { // 不测量性能特征时, 也把数据填 0
                mapMetricNameValue.insert(std::pair<std::string, double>(vecMetricName[i], (double)0.0));
            }
        }

        // std::cout << "ENG_PERF_MEASURER::EndOnce(): Energy = " << mapMetricNameValue["Energy"] << std::endl;
        // std::cout << "ENG_PERF_MEASURER::EndOnce(): Time = " << mapMetricNameValue["Time"] << std::endl;
    }

    // std::cout << "ENG_PERF_MEASURER::EndOnce(): 8" << std::endl;
    
    // 如果所有数据都测量完了
    // std::cout << "ENG_PERF_MEASURER::EndOnce(): mapMetricNameValue.size() = " << mapMetricNameValue.size() << std::endl;
    // for (std::map<std::string, double>::iterator iter = mapMetricNameValue.begin(); iter != mapMetricNameValue.end(); iter++)
    // {
    //     std::cout << "mapMetricNameValue[" << iter->first << "] = " << iter->second << std::endl;
    // }
    
    if ( (isMeasureFullFeature==false) 
        || ( isMeasureFullFeature==true 
            && mapMetricNameValue.size() == 2+vecMetricName.size() ) )
    {
        // 发送该组数据
        SendData(isRecordTrace);
        // std::cout << "ENG_PERF_MEASURER::EndOnce(): SendData()" << std::endl;
    }

    // std::cout << "ENG_PERF_MEASURER::EndOnce(): 9" << std::endl;

    isMeasuring = false;
    pthread_mutex_unlock(&mutexCUDAContext);
    // std::cout << "ENG_PERF_MEASURER::EndOnce(): 10" << std::endl;
    return 0;
}

int ENG_PERF_MEASURER::SendData(bool isTrace){

    // std::cout << "ENG_PERF_MEASURER::SendData()" << std::endl;

    int tmpLen = 0;
    int MsgIndex = 0;
    char Msg[UDP_BUF_LEN_DATA];
    memset(Msg, 0, UDP_BUF_LEN_DATA);

    std::cout << "ENG_PERF_MEASURER::SendData(): Num of Metric = " << mapMetricNameValue.size() << std::endl;
    for (std::map<std::string, double>::iterator  iter = mapMetricNameValue.begin(); iter != mapMetricNameValue.end(); iter++)
    {
        tmpLen = iter->first.size()+1;
        if ( MsgIndex+tmpLen+sizeof(iter->second) >= UDP_BUF_LEN_DATA )
        {
            std::cout << "SendData ERROR: out of UDP_BUF_LEN_DATA" << std::endl;
            exit(1);
        }

        strcpy(&Msg[MsgIndex], iter->first.c_str());
        MsgIndex += tmpLen;
        
        memcpy((void*)&Msg[MsgIndex], (void*)&iter->second, sizeof(iter->second));
        MsgIndex += sizeof(iter->second);
    }
    
    // std::cout << "ENG_PERF_MEASURER::SendData(): isTrace = " << isTrace << std::endl;
    // std::cout << "ENG_PERF_MEASURER::SendData(): isRecordTrace = " << isRecordTrace << std::endl;
    if (isTrace && isRecordTrace)
    {
        // 这里插入 "SampleCount"
        unsigned long long tmpSampleCount;
        tmpSampleCount = PowerMeasurer.SampleCount;

        // std::cout << "SendData: tmpSampleCount = " << tmpSampleCount << std::endl;

        tmpLen = strlen("SampleCount") + 1;
        if ( MsgIndex+tmpLen+sizeof(tmpSampleCount) >= UDP_BUF_LEN_DATA )
        {
            std::cout << "SendData ERROR: out of UDP_BUF_LEN_DATA" << std::endl;
            exit(1);
        }
        strcpy(&Msg[MsgIndex], "SampleCount");
        MsgIndex += tmpLen;

        memcpy((void*)&Msg[MsgIndex], (void*)&tmpSampleCount, sizeof(tmpSampleCount));
        MsgIndex += sizeof(tmpSampleCount);

        if (tmpSampleCount > 0)
        {
            // 加锁 共享内存读写
            pthread_mutex_lock(&lockShm);

            // 如果进程间共享内存不够就 先释放 然后 重新分配
            if (tmpSampleCount > SharedBufLen)
            {
                // 分离共享内存和当前进程
                ret = shmdt(pShmTime);
                if(ret < 0)
                {
                    perror("ENG_PERF_MEASURER: shmdt: Time");
                    exit(1);
                }
                ret = shmdt(pShmPower);
                if(ret < 0)
                {
                    perror("ENG_PERF_MEASURER: shmdt: Energy");
                    exit(1);
                }

                //删除共享内存
                shmctl(shmIDTime, IPC_RMID, NULL);
                shmctl(shmIDPower, IPC_RMID, NULL);

                // 下边创建进程间共享内存, 将 trace数据 拷贝到共享内存
                shmTimeLen = tmpSampleCount * sizeof(double);
                shmIDTime = shmget(keyTime, shmTimeLen, IPC_CREAT|0666);    
                if(shmIDTime < 0){
                    perror("ENG_PERF_MEASURER: shmget: Time");
                    exit(-1);
                }
                shmPowerLen = tmpSampleCount * sizeof(float);
                shmIDPower = shmget(keyPower, shmPowerLen, IPC_CREAT|0666);    
                if(shmIDPower < 0){
                    perror("ENG_PERF_MEASURER: shmget: Energy");
                    exit(-1);
                }
                SharedBufLen = tmpSampleCount;

                // 映射进程间共享内存
                pShmTime = (double*)shmat(shmIDTime, NULL, 0);
                if(pShmTime < 0){
                    perror("ENG_PERF_MEASURER: shmat: Time");
                    _exit(-1);
                }
                pShmPower = (float*)shmat(shmIDPower, NULL, 0);
                if(pShmPower < 0){
                    perror("ENG_PERF_MEASURER: shmat: Energy");
                    _exit(-1);
                }
            }
            
            // 加锁 测量数据缓冲
            // 复制
            pthread_mutex_lock(&PowerMeasurer.lockData);
            memcpy(pShmTime, PowerMeasurer.vecTimeStampCpy.data(), tmpSampleCount * sizeof(double));
            memcpy(pShmPower, PowerMeasurer.vecPowerCpy.data(), tmpSampleCount * sizeof(float));
            pthread_mutex_unlock(&PowerMeasurer.lockData);
            // 解锁 测量数据缓冲

            // 解锁 共享内存读写
            pthread_mutex_unlock(&lockShm);
        }
    }

    // std::cout << "ENG_PERF_MEASURER::SendData(): Msg = ";
    // for (size_t i = 0; i < MsgIndex; i++)
    // {
    //     std::cout << Msg[i];
    // }
    // std::cout << std::endl;

    if (MsgIndex > 0)
    {
        //连接
        if(connect(measurer2manager_fd,(struct sockaddr*)&manager_addr,sizeof(manager_addr)) < 0) {
            printf(" connect socket error: %s(errno :%d)\n",strerror(errno),errno);
            return 0;
        }

        // std::cout << "ENG_PERF_MEASURER::SendData(): 开始发送测量数据" << std::endl;
        sendto(measurer2manager_fd, Msg, MsgIndex, 0, (struct sockaddr*)&manager_addr, SizeofManagerAddr);
    }
    
    // std::cout << "ENG_PERF_MEASURER::SendData(): 结束发送测量数据" << std::endl;

    return 0;
}


int ENG_PERF_MEASURER::InitInCode(int inDeviceIDCUDADrv, int inDeviceIDNVML, RUN_MODE inRunMode, std::vector<std::string> inVecMetricName, bool inIsMeasurePower, bool inIsMeasurePerformace){

    DeviceIDCUDADrv = inDeviceIDCUDADrv;
    DeviceIDNVML = inDeviceIDNVML;

    RunMode = inRunMode;
    isMeasurePower = inIsMeasurePower;
    isMeasurePerformace = inIsMeasurePerformace;
    vecMetricName = inVecMetricName;

    int DeviceCount;
    CHECK_CUDA_DRIVER_ERROR(cuInit(0)); // wfr 20210512 initialize CUDA driver
    // wfr 20210329 ENG_PERF_MEASURER::Init is called at the entry of applications, so CUDA driver should be initialized by itself
    // std::cout << "cuDeviceGetCount" << std::endl;
    CHECK_CUDA_DRIVER_ERROR(cuDeviceGetCount(&DeviceCount));
    std::cout << "ENG_PERF_MEASURER: cuDeviceGetCount: DeviceCount = " << DeviceCount << std::endl;

    // std::cout << "cuDeviceGet" << std::endl;
    std::cout << "DeviceIDCUDADrv = " << DeviceIDCUDADrv << std::endl;
    CHECK_CUDA_DRIVER_ERROR(cuDeviceGet(&cuDevice, DeviceIDCUDADrv));

    CUuuid uuid;
    // std::cout << "cuDeviceGetUuid" << std::endl;
    CHECK_CUDA_DRIVER_ERROR(cuDeviceGetUuid(&uuid, cuDevice));
    std::cout << "uuid = " << std::hex;
    for(int i = 0; i<16; i++){
        std::cout << ((unsigned int)(uuid.bytes[i])&((unsigned int)(0xFF))) << " ";
    }
    std::cout << std::dec << std::endl;

    // CHECK_CUDA_DRIVER_ERROR(cuCtxGetCurrent(&cuContext));

    // if(cuContext==NULL){
    //     std::cout << "ENG_PERF_MEASURER ERROR: Cannot get current cuda context!" << std::endl;
    //     exit(1);
    // }

    // std::cout << "ENG_PERF_MEASURER: cuContext = " << std::hex << (void*)cuContext << std::dec << std::endl;

    // wfr 20210326 enable callback function EPMeasureCallbackHandler() for cuCtxCreate() to get cuContext and begin EPMeasurer
    CUpti_SubscriberHandle subscriber;
    CUPTI_API_CALL(cuptiSubscribe(&subscriber, (CUpti_CallbackFunc)EPMeasureCallbackHandler, (void*)this));
    CUPTI_API_CALL(cuptiEnableCallback(1, subscriber, CUPTI_CB_DOMAIN_RESOURCE, CUPTI_CBID_RESOURCE_CONTEXT_CREATED));
    CUPTI_API_CALL(cuptiEnableCallback(1, subscriber, CUPTI_CB_DOMAIN_RESOURCE, CUPTI_CBID_RESOURCE_CONTEXT_DESTROY_STARTING));

    if (isMeasurePower == true)
    {
        PowerMeasurer.Init(DeviceIDNVML, &MyNVML);
        // std::cout << "PowerMeasurer.Init()" << std::endl;
    }

    if (isMeasurePerformace == true)
    {
        CUpti_Profiler_Initialize_Params profilerInitializeParams = {CUpti_Profiler_Initialize_Params_STRUCT_SIZE};
        CHECK_CUPTI_ERROR(cuptiProfilerInitialize(&profilerInitializeParams));
        /* Get chip name for the cuda  device */
        CUpti_Device_GetChipName_Params getChipNameParams = { CUpti_Device_GetChipName_Params_STRUCT_SIZE };
        getChipNameParams.deviceIndex = DeviceIDCUDADrv;
        CHECK_CUPTI_ERROR(cuptiDeviceGetChipName(&getChipNameParams));
        chipName = getChipNameParams.pChipName;

        /* Generate configuration for metrics, this can also be done offline*/
        NVPW_InitializeHost_Params initializeHostParams = { NVPW_InitializeHost_Params_STRUCT_SIZE };
        CHECK_NVPW_ERROR(NVPW_InitializeHost(&initializeHostParams));

        beginSessionParams = {CUpti_Profiler_BeginSession_Params_STRUCT_SIZE};
        setConfigParams = {CUpti_Profiler_SetConfig_Params_STRUCT_SIZE};
        enableProfilingParams = {CUpti_Profiler_EnableProfiling_Params_STRUCT_SIZE};
        disableProfilingParams = {CUpti_Profiler_DisableProfiling_Params_STRUCT_SIZE};
        pushRangeParams = {CUpti_Profiler_PushRange_Params_STRUCT_SIZE};
        popRangeParams = {CUpti_Profiler_PopRange_Params_STRUCT_SIZE};
    }

    return 0;
}

int ENG_PERF_MEASURER::BeginInCode(){ // 仅仅用来测量需要插入源代码中
    mapMetricNameValue.clear();
    mapMetricNameValue.insert({ { "Energy", (double)0.0 }, {"Time", (double)0.0} });

    if (isMeasurePerformace==true)
    {
        counterDataImagePrefix.clear();
        configImage.clear();
        counterDataImage.clear();
        counterDataScratchBuffer.clear();
        metricNameValueMap.clear();
        mapMetricNameValue.clear();
        // std::string CounterDataFileName("SimpleCupti.counterdata");
        // std::string CounterDataSBFileName("SimpleCupti.counterdataSB");
        CUpti_ProfilerReplayMode profilerReplayMode = CUPTI_UserReplay;
        CUpti_ProfilerRange profilerRange = CUPTI_UserRange;
        // CUPTI_UserReplay CUPTI_KernelReplay
        // CUPTI_UserRange CUPTI_AutoRange

        if (vecMetricName.size()) {
            if(!NV::Metric::Config::GetConfigImage(chipName, vecMetricName, configImage)){
                std::cout << "Failed to create configImage" << std::endl;
                exit(-1);
            }
            if(!NV::Metric::Config::GetCounterDataPrefixImage(chipName, vecMetricName, counterDataImagePrefix)){
                std::cout << "Failed to create counterDataImagePrefix" << std::endl;
                exit(-1);
            }
        }else{
            std::cout << "No metrics provided to profile" << std::endl;
            exit(-1);
        }

        if(!CreateCounterDataImage(counterDataImage, counterDataScratchBuffer, counterDataImagePrefix))
        {
            std::cout << "Failed to create counterDataImage" << std::endl;
            exit(-1);
        }

        beginSessionParams.ctx = NULL; // cuContext
        beginSessionParams.counterDataImageSize = counterDataImage.size();
        beginSessionParams.pCounterDataImage = &counterDataImage[0];
        beginSessionParams.counterDataScratchBufferSize = counterDataScratchBuffer.size();
        beginSessionParams.pCounterDataScratchBuffer = &counterDataScratchBuffer[0];
        beginSessionParams.range = profilerRange;
        beginSessionParams.replayMode = profilerReplayMode;
        beginSessionParams.maxRangesPerPass = maxRangesPerPass;
        beginSessionParams.maxLaunchesPerPass = maxLaunchesPerPass;

        CHECK_CUPTI_ERROR(cuptiProfilerBeginSession(&beginSessionParams));

        setConfigParams.pConfig = &configImage[0];
        setConfigParams.configSize = configImage.size();

        setConfigParams.passIndex = 0;
        setConfigParams.minNestingLevel = minNestingLevel;
        setConfigParams.numNestingLevels = numNestingLevels;
        CHECK_CUPTI_ERROR(cuptiProfilerSetConfig(&setConfigParams));
        /* User takes the resposiblity of replaying the kernel launches */

        // CUPTI_API_CALL(cuptiProfilerEnableProfiling(&enableProfilingParams));
        // wfr 20201021 为了验证 replay 的逻辑：是只重复运行 kernel，还是重复运行 cuptiProfilerEnableProfiling 和 cuptiProfilerDisableProfiling 之间的代码。
        // std::cout << "CUPTI_KernelReplay: between cuptiProfilerEnableProfiling and cuptiProfilerDisableProfiling" << std::endl;

        beginPassParams = {CUpti_Profiler_BeginPass_Params_STRUCT_SIZE};

        std::string rangeName = "userrangeA";
        pushRangeParams.pRangeName = rangeName.c_str();

        CHECK_CUPTI_ERROR(cuptiProfilerBeginPass(&beginPassParams));
        CHECK_CUPTI_ERROR(cuptiProfilerEnableProfiling(&enableProfilingParams));
        CHECK_CUPTI_ERROR(cuptiProfilerPushRange(&pushRangeParams));
    }

    if (isMeasurePower==true)
    {
        PowerMeasurer.Reset();
        PowerMeasurer.Begin(true);
    }

    // CUPTI 只能测量完整的 kernel, 即测量时间区间刚开始和快结束时的不完整 kernel 不会被测量, 
    // 而能耗和时间的测量是确确实实持续整个测量时间区间的, 
    // 这样就导致 性能特征 和 能耗/时间 的测量不匹配 .........
    // ??? 这个问题需要解决, 
    // 一个可能的技术路线是, 查查 kernel 启动/结束 有没有给提供可用的钩子函数啥的
    // 在钩子函数中启动 能耗测量 并 打时间戳

    return 0;
}

int ENG_PERF_MEASURER::EndInCode(std::map<std::string, double>& inMapMetricNameValue){ // 仅仅用来测量需要插入源代码中

    if (0 == mapMetricNameValue.size())
    {
        EndInCode();
    }
    inMapMetricNameValue = mapMetricNameValue;

    return 0;
}

int ENG_PERF_MEASURER::EndInCode(){ // 仅仅用来测量需要插入源代码中

    if (isMeasurePower==true)
    {
        PowerMeasurer.End();
        mapMetricNameValue["Energy"] = PowerMeasurer.EnergyAT;
        mapMetricNameValue["Time"] = PowerMeasurer.ActualDuration;
    }

    if (isMeasurePerformace==true)
    {
        // CHECK_CUPTI_ERROR(cuptiProfilerDisableProfiling(&disableProfilingParams));

        CHECK_CUPTI_ERROR(cuptiProfilerPopRange(&popRangeParams));
        CHECK_CUPTI_ERROR(cuptiProfilerDisableProfiling(&disableProfilingParams));
        endPassParams = {CUpti_Profiler_EndPass_Params_STRUCT_SIZE};
        CHECK_CUPTI_ERROR(cuptiProfilerEndPass(&endPassParams));

        flushCounterDataParams = {CUpti_Profiler_FlushCounterData_Params_STRUCT_SIZE};
        CHECK_CUPTI_ERROR(cuptiProfilerFlushCounterData(&flushCounterDataParams));
        unsetConfigParams = {CUpti_Profiler_UnsetConfig_Params_STRUCT_SIZE};
        CHECK_CUPTI_ERROR(cuptiProfilerUnsetConfig(&unsetConfigParams));
        endSessionParams = {CUpti_Profiler_EndSession_Params_STRUCT_SIZE};
        CHECK_CUPTI_ERROR(cuptiProfilerEndSession(&endSessionParams));

        /* Evaluation of metrics collected in counterDataImage, this can also be done offline*/
        // std::cout << "ENG_PERF_MEASURER::EndOnce(): PrintMetricValues" << std::endl;
        // NV::Metric::Eval::PrintMetricValues(chipName, counterDataImage, vecMetricName);
        // std::cout << "ENG_PERF_MEASURER::EndOnce(): PrintMetricValues" << std::endl;
        NV::Metric::Eval::GetMetricGpuValue(chipName, counterDataImage, vecMetricName, metricNameValueMap);
        // std::cout << "ENG_PERF_MEASURER::EndOnce(): metricNameValueMap.size() = " << metricNameValueMap.size() << std::endl;

        // 累加不同 range 的数据
        for(unsigned int i = 0; i<metricNameValueMap.size(); i++){
            double SumValue = 0.0;
            for (size_t j = 0; j < metricNameValueMap[i].rangeNameMetricValueMap.size(); j++)
            {
                SumValue += metricNameValueMap[i].rangeNameMetricValueMap[j].second;
            }
            
            mapMetricNameValue.insert(std::pair<std::string, double>(metricNameValueMap[i].metricName, SumValue));
        }
    }
    
    // 如果所有数据都测量完了，打印测量到的数据
    // std::cout << "ENG_PERF_MEASURER::EndInCode(): mapMetricNameValue.size() = " << mapMetricNameValue.size() << std::endl;
    // std::cout << "ENG_PERF_MEASURER::EndInCode(): vecMetricName.size() = " << vecMetricName.size() << std::endl;
    // for (std::map<std::string, double>::iterator  iter = mapMetricNameValue.begin(); iter != mapMetricNameValue.end(); iter++)
    // {
    //     std::cout << "mapMetricNameValue[" << iter->first << "] = " << iter->second << std::endl;
    // }

    return 0;
}



ENG_PERF_MEASURER::ENG_PERF_MEASURER(){
    // std::cout << "ENG_PERF_MEASURER::ENG_PERF_MEASURER()" << std::endl;
    Init();
}

ENG_PERF_MEASURER::~ENG_PERF_MEASURER(){
    // std::cout << "ENG_PERF_MEASURER::~ENG_PERF_MEASURER()" << std::endl;

    close(manager2measurer_fd);
    close(measurer2manager_fd);
    
    // std::cout << "ENG_PERF_MEASURER::~ENG_PERF_MEASURER(): 0" << std::endl;

    //分离共享内存和当前进程
    ret = shmdt(pShmTime);
    if(ret < 0)
    {
        perror("ENG_PERF_MEASURER: shmdt: Time");
        exit(1);
    }
    ret = shmdt(pShmPower);
    if(ret < 0)
    {
        perror("ENG_PERF_MEASURER: shmdt: Energy");
        exit(1);
    }

    // std::cout << "ENG_PERF_MEASURER::~ENG_PERF_MEASURER(): 1" << std::endl;

    //删除共享内存
    shmctl(shmIDTime, IPC_RMID, NULL);
    shmctl(shmIDPower, IPC_RMID, NULL);

    std::cout << "ENG_PERF_MEASURER::~ENG_PERF_MEASURER(): 2" << std::endl;
}


bool CreateCounterDataImage(
    std::vector<uint8_t>& counterDataImage,
    std::vector<uint8_t>& counterDataScratchBuffer,
    std::vector<uint8_t>& counterDataImagePrefix)
{

    CUpti_Profiler_CounterDataImageOptions counterDataImageOptions;
    counterDataImageOptions.pCounterDataPrefix = &counterDataImagePrefix[0];
    counterDataImageOptions.counterDataPrefixSize = counterDataImagePrefix.size();
    counterDataImageOptions.maxNumRanges = maxNumRanges;
    counterDataImageOptions.maxNumRangeTreeNodes = maxNumRangeTreeNodes;
    counterDataImageOptions.maxRangeNameLength = maxRangeNameLength;

    CUpti_Profiler_CounterDataImage_CalculateSize_Params calculateSizeParams = {CUpti_Profiler_CounterDataImage_CalculateSize_Params_STRUCT_SIZE};

    calculateSizeParams.pOptions = &counterDataImageOptions;
    calculateSizeParams.sizeofCounterDataImageOptions = CUpti_Profiler_CounterDataImageOptions_STRUCT_SIZE;

    CHECK_CUPTI_ERROR(cuptiProfilerCounterDataImageCalculateSize(&calculateSizeParams));

    CUpti_Profiler_CounterDataImage_Initialize_Params initializeParams = {CUpti_Profiler_CounterDataImage_Initialize_Params_STRUCT_SIZE};
    initializeParams.sizeofCounterDataImageOptions = CUpti_Profiler_CounterDataImageOptions_STRUCT_SIZE;
    initializeParams.pOptions = &counterDataImageOptions;
    initializeParams.counterDataImageSize = calculateSizeParams.counterDataImageSize;

    counterDataImage.resize(calculateSizeParams.counterDataImageSize);
    initializeParams.pCounterDataImage = &counterDataImage[0];
    CHECK_CUPTI_ERROR(cuptiProfilerCounterDataImageInitialize(&initializeParams));

    CUpti_Profiler_CounterDataImage_CalculateScratchBufferSize_Params scratchBufferSizeParams = {CUpti_Profiler_CounterDataImage_CalculateScratchBufferSize_Params_STRUCT_SIZE};
    scratchBufferSizeParams.counterDataImageSize = calculateSizeParams.counterDataImageSize;
    scratchBufferSizeParams.pCounterDataImage = initializeParams.pCounterDataImage;
    CHECK_CUPTI_ERROR(cuptiProfilerCounterDataImageCalculateScratchBufferSize(&scratchBufferSizeParams));

    counterDataScratchBuffer.resize(scratchBufferSizeParams.counterDataScratchBufferSize);

    CUpti_Profiler_CounterDataImage_InitializeScratchBuffer_Params initScratchBufferParams = {CUpti_Profiler_CounterDataImage_InitializeScratchBuffer_Params_STRUCT_SIZE};
    initScratchBufferParams.counterDataImageSize = calculateSizeParams.counterDataImageSize;

    initScratchBufferParams.pCounterDataImage = initializeParams.pCounterDataImage;
    initScratchBufferParams.counterDataScratchBufferSize = scratchBufferSizeParams.counterDataScratchBufferSize;
    initScratchBufferParams.pCounterDataScratchBuffer = &counterDataScratchBuffer[0];

    CHECK_CUPTI_ERROR(cuptiProfilerCounterDataImageInitializeScratchBuffer(&initScratchBufferParams));

    return true;
}