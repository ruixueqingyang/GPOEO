
/*******************************************************************************
Copyright(C), 2020-2020, 瑞雪轻飏
     FileName: PowerMeasurer.cpp
       Author: 瑞雪轻飏
      Version: 0.01
Creation Date: 20200804
  Description: 能耗测量
       Others: 
*******************************************************************************/

#include "PowerMeasure.h"

EPOPT_NVML MyNVML;
POWER_MEASURE PowerMeasurer(&MyNVML);

void sleepbyselect(struct timeval tv)
{
    int err;
    do {
        err = select(0, NULL, NULL, NULL, &tv);
    } while(err < 0 && errno == EINTR);
}

static void Sampler(int signum){

    if(signum != SIGALRM) return;

    gettimeofday(&PowerMeasurer.currTimeStamp, NULL);

    // get current value
    unsigned int tmpPower;
    PowerMeasurer.nvmlResult = nvmlDeviceGetPowerUsage(PowerMeasurer.nvmlDevice, &tmpPower);
    if (NVML_SUCCESS != PowerMeasurer.nvmlResult) {
        printf("Failed to get power usage: %s\n", nvmlErrorString(PowerMeasurer.nvmlResult));
        // exit(-1);
        PowerMeasurer.currPower = 0;
    }
    PowerMeasurer.currPower = (float)tmpPower / 1000;
    

    // update min/max and push data
    if(PowerMeasurer.currPower < PowerMeasurer.minPower){
        PowerMeasurer.minPower = PowerMeasurer.currPower;
    }
    if(PowerMeasurer.currPower > PowerMeasurer.maxPower){
        PowerMeasurer.maxPower = PowerMeasurer.currPower;
    }
    
    double ActualInterval; // (s)
    double RelativeTimeStamp; // (s)
    // calculate ActualInterval/sum value, and push timestamp
    if(PowerMeasurer.isFisrtSample==true){
        PowerMeasurer.isFisrtSample = false;

        PowerMeasurer.StartTimeStamp = (double)PowerMeasurer.currTimeStamp.tv_sec + (double)PowerMeasurer.currTimeStamp.tv_usec * 1e-6;

        RelativeTimeStamp = 0.0;
    }else{
        ActualInterval = (double)(PowerMeasurer.currTimeStamp.tv_sec - PowerMeasurer.prevTimeStamp.tv_sec) + (double)(PowerMeasurer.currTimeStamp.tv_usec - PowerMeasurer.prevTimeStamp.tv_usec) * 1e-6;

        RelativeTimeStamp = (double)PowerMeasurer.currTimeStamp.tv_sec + (double)PowerMeasurer.currTimeStamp.tv_usec * 1e-6 - PowerMeasurer.StartTimeStamp;

        PowerMeasurer.ActualDuration = RelativeTimeStamp;
        
        PowerMeasurer.Energy += (float)(PowerMeasurer.prevPower + PowerMeasurer.currPower) / 2 * ActualInterval;
    }

    // wfr 20201221
    PowerMeasurer.vecPower.push_back(PowerMeasurer.currPower);
    PowerMeasurer.vecTimeStamp.push_back(RelativeTimeStamp);

    // wfr 20201221 如果可以获得锁, 就同步 采样数据数组的副本, 本次不能获得锁, 则等以后再同步
    if (0 == pthread_mutex_trylock(&PowerMeasurer.lockData))
    {
        // 将 Cpy vector 与 vector 同步
        PowerMeasurer.vecPowerCpy.insert(PowerMeasurer.vecPowerCpy.end(), PowerMeasurer.vecPower.begin()+PowerMeasurer.vecPowerCpy.size(), PowerMeasurer.vecPower.end());

        PowerMeasurer.vecTimeStampCpy.insert(PowerMeasurer.vecTimeStampCpy.end(), PowerMeasurer.vecTimeStamp.begin()+PowerMeasurer.vecTimeStampCpy.size(), PowerMeasurer.vecTimeStamp.end());

        pthread_mutex_unlock(&PowerMeasurer.lockData);
    }
    

    // update previous value
    PowerMeasurer.prevTimeStamp.tv_sec = PowerMeasurer.currTimeStamp.tv_sec;
    PowerMeasurer.prevTimeStamp.tv_usec = PowerMeasurer.currTimeStamp.tv_usec;
    PowerMeasurer.prevPower = PowerMeasurer.currPower;

    // update SampleCount
    PowerMeasurer.SampleCount++;
}

int POWER_MEASURE::Begin(bool inIsRecordTrace){

    isRecordTrace = inIsRecordTrace;

    // NVML INITIALIZATIONS
    pMyNVML->Init();

    nvmlResult = nvmlDeviceGetHandleByIndex(DeviceID, &nvmlDevice);
	if (NVML_SUCCESS != nvmlResult)
	{
		printf("Failed to get handle for device %d: %s\n", DeviceID, nvmlErrorString(nvmlResult));
		return -1;
	}

    // 注册时钟信号，启动采样
    signal(SIGALRM, Sampler);
    // ualarm(10, SampleInterval*1000);

    // std::cout << "POWER_MEASURE::Begin: isRecordTrace = " << isRecordTrace << std::endl;

    struct itimerval tick;
    
    memset(&tick, 0, sizeof(tick));

    //Timeout to run first time
    tick.it_value.tv_sec = 0;
    tick.it_value.tv_usec = 5000;

    //After first, the Interval time for clock
    tick.it_interval.tv_sec = 0;
    tick.it_interval.tv_usec = SampleInterval*1000;

    if(setitimer(ITIMER_REAL, &tick, NULL) < 0){ // stsrt sampling timer
        std::cout << "Set timer failed!" << std::endl;
    }else{
        // std::cout << "PowerMeasure: SampleInterval = " << SampleInterval << std::endl;
        // std::cout << "Sampling has already started." << std::endl;
        // std::cout << "Sampling..." << std::endl;
    }

    // std::cout << "POWER_MEASURE::Begin: setitimer" << std::endl;

    return 0;
}

int POWER_MEASURE::End(){
    struct itimerval tick;
    
    memset(&tick, 0, sizeof(tick));

    // std::cout << "POWER_MEASURE::End: memset" << std::endl;

    //Timeout to run first time
    tick.it_value.tv_sec = 0;
    tick.it_value.tv_usec = 0;

    //After first, the Interval time for clock
    tick.it_interval.tv_sec = 0;
    tick.it_interval.tv_usec = 0;

    setitimer(ITIMER_REAL, &tick, NULL); // stop sampling timer

    // 等待两个测量间隔, 确保完成最后一次测量
    struct timeval tv;
    tv.tv_sec = 0;
    tv.tv_usec = 2 * 1000 * SampleInterval;
    sleepbyselect(tv);
    // usleep(2 * 1000 * SampleInterval);

    // std::cout << "POWER_MEASURE::End: ActualDuration = " << ActualDuration << std::endl;

    avgPower = Energy / ActualDuration;
    EnergyAT = Energy - PowerThreshold*ActualDuration;

    // std::cout << "POWER_MEASURE::End: SampleCount = " << SampleCount << std::endl;

    pMyNVML->Uninit();

    return 0;
}

int POWER_MEASURE::Init(EPOPT_NVML* inpNVML){

    pMyNVML = inpNVML;

    DeviceID = -1;
    SampleInterval = SAMPLE_INTERVAL;
    PowerThreshold = POWER_THRESHOLD;

    vecTimeStamp.clear();
    vecTimeStamp.reserve(VECTOR_RESERVE);
    vecPower.clear();
    vecPower.reserve(VECTOR_RESERVE);
    vecTimeStampCpy.clear();
    vecTimeStampCpy.reserve(VECTOR_RESERVE);
    vecPowerCpy.clear();
    vecPowerCpy.reserve(VECTOR_RESERVE);

    pthread_mutex_init(&lockData, NULL);
    pthread_mutex_unlock(&lockData);

    isFisrtSample = true;
    isMeasuring = 0;
    isRecordTrace = true;

    SampleCount = 0;
    ActualDuration = 0.0;
    StartTimeStamp = 0.0;
    minPower = 1e9; maxPower = 0.0; avgPower = 0.0; Energy = 0.0; EnergyAT = 0.0;

    prevTimeStamp.tv_sec = 0;
    prevTimeStamp.tv_usec = 0;

    return 0;
}

int POWER_MEASURE::Init(int inDeviceID, EPOPT_NVML* inpNVML, std::string inOutFilePath, bool inIsRecordTrace, float inSampleInterval, float inPowerThreshold){
    DeviceID = inDeviceID;
    OutFilePath = inOutFilePath;
    isRecordTrace = inIsRecordTrace;
    SampleInterval = inSampleInterval;
    PowerThreshold = inPowerThreshold;
    pMyNVML = inpNVML;

    if(OutFilePath.size()>0){
        outStream.open(OutFilePath, std::ifstream::out);
        if(!outStream.is_open()){
            outStream.close();
            std::cerr << "ERROR: failed to open output file" << std::endl;
        }
    }

    return 0;
}

int POWER_MEASURE::Reset(){

    isFisrtSample = true;
    isMeasuring = 0;
    isRecordTrace = true;

    SampleCount = 0;
    ActualDuration = 0.0;
    StartTimeStamp = 0.0;
    minPower = 1e9; maxPower = 0.0; avgPower = 0.0; Energy = 0.0; EnergyAT = 0.0;
    prevTimeStamp.tv_sec = 0;
    prevTimeStamp.tv_usec = 0;

    vecTimeStamp.clear();
    vecTimeStampCpy.clear();
    vecPower.clear();
    vecPowerCpy.clear();

    outStream.close();

    return 0;
}

POWER_MEASURE::POWER_MEASURE(EPOPT_NVML* inpNVML){
    Init(inpNVML);
}

POWER_MEASURE::POWER_MEASURE(int inDeviceID, EPOPT_NVML* inpNVML, std::string inOutFilePath, bool inIsRecordTrace, float inSampleInterval, float inPowerThreshold){
    Init(inDeviceID, inpNVML, inOutFilePath, inIsRecordTrace, inSampleInterval, inPowerThreshold);
}

POWER_MEASURE::~POWER_MEASURE(){
    pMyNVML->Uninit();
}