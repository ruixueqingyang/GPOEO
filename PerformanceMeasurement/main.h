/*******************************************************************************
Copyright(C), 2020-2020, 瑞雪轻飏
     FileName: main.h
       Author: 瑞雪轻飏
      Version: 0.01
Creation Date: 20200506
  Description: 1. 包含各种头文件
               2. 定义 配置信息类(CONFIG) 以及 测量数据类(PERF_DATA)
       Others: //其他内容说明
*******************************************************************************/

#ifndef __MAIN_H
#define __MAIN_H

#include <stdio.h>
#include <stdlib.h>
#include <iostream>
#include <iomanip>
#include <vector>
#include <system_error>
#include <string.h>
#include <vector>
#include <assert.h>
#include <math.h>
#include <fstream>
#include <sstream>
#include <math.h>

#include <pthread.h>
#include <unistd.h>
#include <getopt.h>
#include <nvml.h>
#include <signal.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <sys/time.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <signal.h>
#include <semaphore.h>


#include <cuda.h>
#include <cuda_runtime.h>
#include "PowerManager.h"

pthread_cond_t condTStart; // control children processes to start simultaneously
pthread_mutex_t mutexTStart; // mutex for condTStart

unsigned int ChlidWaitCount;
unsigned int ChlidFinishCount; // Initial value is 0; ChlidFinishCount++ when a child thread/process finished; main thread check the value of ChlidFinishCount to know whether all child finished
pthread_cond_t condTEnd; // Child thread sends condTEnd to main thread when the child thread finished
pthread_mutex_t mutexTEnd; // mutex for condTStart

sem_t semPEnd; // semaphores control children processes of applications

pthread_mutex_t lockValidFlag;
pthread_mutex_t lockMsgHandlerSource;

#define VECTOR_RESERVE 20000
#define SERVER_PORT 7777
#define BUFF_LEN 1024
// #define BUFF_LEN 128
#define NUM_BUFFS 8
#define NUM_APP_STAMPS 128

enum MEASURE_MODE {
    INTERACTION,
    // DURATION,
    APPLICATION,
    DAEMON
};

class CONFIG {
public:

    MEASURE_MODE MeasureMode;

    bool isGenOutFile, isTrace, isMeasureEnergy, isMeasureMemUtil, isMeasureMemClk, isMeasureGPUUtil, isMeasureSMClk;
    bool istrategy;

    int DeviceID;
    std::string OutFilePath;

    float SampleInterval; // (ms) Sampling Interval
    float PowerThreshold; // (W) Part of power above this threshold is consider as dynamic power consumed by applications
    // float MeasureDuration; // (s) Sampling will keep for the specific measurement duration
    float PostInterval; // (s) Sampling will keep for the specific time interval after all applications are completed

    std::vector< char* > vecAppPath;
    std::vector< char** > vecAppAgrv;

    void init();
    void Reset(std::string OutPath="");
    int LoadAppList(char* AppListPath);

    CONFIG(){
        init();
    }
    ~CONFIG();
};

CONFIG::~CONFIG(){
    for(size_t i = 0; i < vecAppPath.size(); i++){
        if(vecAppPath[i] != NULL){
            free(vecAppPath[i]);
            vecAppPath[i] = NULL;
        }
    }

    for(size_t i = 0; i < vecAppAgrv.size(); i++){
        if(vecAppAgrv[i] != NULL){

            size_t j = 0;
            while(vecAppAgrv[i][j] != NULL){
                free(vecAppAgrv[i][j]);
                vecAppAgrv[i][j] = NULL;
                j++;
            }
            
            free(vecAppAgrv[i]);
            vecAppAgrv[i] = NULL;
        }
    }
}

int CONFIG::LoadAppList(char* AppListPath){

    // std::string src = AppListPath;

    std::ifstream srcStream(AppListPath, std::ifstream::in); // |std::ifstream::binary
    if(!srcStream.is_open()){
        srcStream.close();
        std::cerr << "ERROR: failed to open application list file" << std::endl;
        exit(1);
    }

    std::string TmpStr;
    const char* delim = " \r"; // 一行中 使用 空格 分词

    std::getline(srcStream, TmpStr);
    while(!TmpStr.empty()){ // 读取一行

        char* pCharBuff = (char*)malloc( sizeof(char) * (TmpStr.length()+1) );
        strcpy(pCharBuff, TmpStr.c_str());

        // 读取第一个 词, 即应用可执行文件路径
        char* TmpPtrChar = strtok(pCharBuff, delim);

        vecAppPath.emplace_back( (char*)malloc( sizeof(char) * (strlen(TmpPtrChar)+1) ) );
        strcpy(vecAppPath.back(), TmpPtrChar);

        std::vector<char*> TmpVecArg;

        // 这里要处理 TmpVecArg[0], 复制可执行文件/命令, 而不要前边的路径
        std::string TmpStr1 = vecAppPath.back();
        size_t found = TmpStr1.find_last_of('/');
        TmpStr1 = TmpStr1.substr(found+1);
        TmpVecArg.emplace_back( (char*)malloc( sizeof(char) * (TmpStr1.length()+1) ) );
        strcpy(TmpVecArg.back(), TmpStr1.c_str());

        while( ( TmpPtrChar = strtok(NULL, delim) ) ){
            TmpVecArg.emplace_back( (char*)malloc( sizeof(char) * (strlen(TmpPtrChar)+1) ) );
            strcpy(TmpVecArg.back(), TmpPtrChar);
        }

        vecAppAgrv.emplace_back( (char**)malloc( sizeof(char*)*(TmpVecArg.size()+1) ) );
        vecAppAgrv.back()[TmpVecArg.size()] = NULL;

        for(size_t i = 0; i < TmpVecArg.size(); i++){
            vecAppAgrv.back()[i] = TmpVecArg[i];
        }

        free(pCharBuff);
        TmpStr.clear();
        std::getline(srcStream, TmpStr);
    }
    
    srcStream.close();

    return 0;
}

void CONFIG::Reset(std::string OutPath){
    if(MeasureMode != MEASURE_MODE::DAEMON){
        std::cout << "WARNING: MEASURE_MODE is not INTERACTION, do nothing!" << std::endl;
        return;
    }
    istrategy = false;
    if(OutPath.empty()==true){
        isGenOutFile = false;
        OutFilePath.clear();
    }else{
        isGenOutFile = true;
        OutFilePath = OutPath;
    }
}

void CONFIG::init(){

    MeasureMode = MEASURE_MODE::INTERACTION;

    isGenOutFile = false;
    OutFilePath.clear();
    isTrace = false;
    isMeasureEnergy = true;
    isMeasureMemUtil = true;
    isMeasureMemClk = true;
    isMeasureGPUUtil = true;
    isMeasureSMClk = true;
    istrategy = false;

    DeviceID = 1;

    SampleInterval = 20.0;
    PowerThreshold = 1.65;
    // MeasureDuration = -1.0;
    PostInterval = 0.0;
}

class PERF_DATA{
public:

    std::ofstream outStream;

    // 这里是测量过程中的状态，用来管理测量过程：启动，停止等
    bool isFisrtSample;
    CUdevice cuDevice;
    nvmlDevice_t nvmlDevice;
    int ComputeCapablityMajor;
    int ComputeCapablityMinor;
    int isMeasuring; // 采样启动计数，每遇到一个启动请求++，每遇到一个停止请求--，到0才能停止



    unsigned int long long SampleCount;
    double TotalDuration; // (s)

    struct timeval prevTimeStamp, currTimeStamp;
    std::vector<double> vecTimeStamp; // (s)
    double StartTimeStamp; // (s)
    
    unsigned int prevPower, currPower; // (mW)
    nvmlUtilization_t prevUtil, currUtil; // (%)
    unsigned int prevMemClk, currMemClk, prevSMClk, currSMClk; // (MHz)
    // float prevMemUtil, currGPUUtil;
    std::vector<unsigned int> vecPower, vecMemUtil, vecMemClk, vecGPUUtil, vecSMClk; // (mW, %, MHz, %, MHz)

    std::vector< double > vecAppStamp; // 用来保存时间戳，这样就可以对测量进行分段，知道每段时间内的能耗
    std::vector< double > vecAppStampEnergy; // 对应时间戳时刻的 累计的 能耗
    std::vector< std::string > vecAppStampDescription; // 时间戳的文字描述


    unsigned int minPower, maxPower; // (mW, mW)
    float avgPower, Energy; // (mW, mJ)

    unsigned int minMemUtil, maxMemUtil; // (%, %)
    float avgMemUtil, sumMemUtil; // (%, %)

    unsigned int minMemClk, maxMemClk; // (MHz, MHz)
    float avgMemClk, sumMemClk; // (MHz, MHz)

    unsigned int minGPUUtil, maxGPUUtil; // (%, %)
    float avgGPUUtil, sumGPUUtil; // (%, %)

    unsigned int minSMClk, maxSMClk; // (MHz, MHz)
    float avgSMClk, sumSMClk; // (MHz, MHz)

    int SummaryOut(CONFIG& Config, bool isInit){

        // wfr 20210528 set cursor to the beginning of file
        outStream.seekp(0, std::ios::beg);

        std::stringstream tmpStream;

        tmpStream.clear();
        tmpStream.str("");
        tmpStream << "-------- Performance Measurement Results --------" << std::setiosflags(std::ios::right|std::ios::fixed) << std::setfill(' ') << std::setprecision(2) << std::endl;
        tmpStream << "Actual Measurement Duration: " << std::setw(12) << TotalDuration << " s" << std::endl;
        tmpStream << "Actual Sampling Count: " << std::setw(8) << SampleCount << std::endl;

        if (isInit == false)
        {
            std::cout << tmpStream.str();
        }

        if(Config.isGenOutFile==true){
            outStream << tmpStream.str();
        }
        
        if(Config.isMeasureEnergy==true){
            avgPower = Energy / TotalDuration;

            tmpStream.clear();
            tmpStream.str("");
            tmpStream << std::endl;
            tmpStream << "-------- Energy&Power (All) --------" << std::endl;
            tmpStream << "Energy: " << std::setw(12) << Energy/1000 << " J" << std::endl;
            tmpStream << "minPower: " << std::setw(6) << ((float)minPower)/1000 << " W; avgPower: " << std::setw(6) << avgPower/1000 << " W; maxPower: " << std::setw(6) << ((float)maxPower)/1000 << " W" << std::endl;

            if (isInit == false)
            {
                std::cout << tmpStream.str();
            }
            if(Config.isGenOutFile==true){
                outStream << tmpStream.str();
            }
        }


        if(Config.isMeasureEnergy==true){
            avgPower = Energy / TotalDuration;
            float EnergyAbove = Energy/1000 - Config.PowerThreshold*TotalDuration;

            tmpStream.clear();
            tmpStream.str("");
            tmpStream << std::endl;
            tmpStream << "-------- Energy&Power (Above Threshold) --------" << std::endl;
            tmpStream << "Power Threshold: " << std::setw(6) << Config.PowerThreshold << " W" << std::endl;
            tmpStream << "Energy: " << std::setw(12) << EnergyAbove << " J" << std::endl;
            tmpStream << "minPower: " << std::setw(6) << ((float)minPower)/1000-Config.PowerThreshold << " W; avgPower: " << std::setw(6) << avgPower/1000-Config.PowerThreshold << " W; maxPower: " << std::setw(6) << ((float)maxPower)/1000-Config.PowerThreshold << " W" << std::endl;

            if (isInit == false)
            {
                std::cout << tmpStream.str();
            }
            if(Config.isGenOutFile==true){
                outStream << tmpStream.str();
            }
        }

        if(Config.isMeasureGPUUtil==true || Config.isMeasureSMClk==true){

            tmpStream.clear();
            tmpStream.str("");
            tmpStream << std::endl;
            tmpStream << "-------- GPU SM --------" << std::endl;

            if (isInit == false)
            {
                std::cout << tmpStream.str();
            }
            if(Config.isGenOutFile==true){
                outStream << tmpStream.str();
            }
        }
        if(Config.isMeasureGPUUtil==true){
            avgGPUUtil = sumGPUUtil / TotalDuration;

            tmpStream.clear();
            tmpStream.str("");
            tmpStream << "minGPUUtil: " << std::setw(6) << minGPUUtil << " %; avgGPUUtil: " << std::setw(6) << avgGPUUtil << " %; maxGPUUtil: " << std::setw(6) << maxGPUUtil << " %" << std::endl;
            
            if (isInit == false)
            {
                std::cout << tmpStream.str();
            }
            if(Config.isGenOutFile==true){
                outStream << tmpStream.str();
            }
        }
        if(Config.isMeasureSMClk==true){
            avgSMClk= sumSMClk / TotalDuration;

            tmpStream.clear();
            tmpStream.str("");
            tmpStream << "minSMClk: " << std::setw(7) << minSMClk << " MHz; avgSMClk: " << std::setw(7) << avgSMClk << " MHz; maxSMClk: " << std::setw(7) << maxSMClk << " MHz" << std::endl;

            if (isInit == false)
            {
                std::cout << tmpStream.str();
            }
            if(Config.isGenOutFile==true){
                outStream << tmpStream.str();
            }
        }

        if(Config.isMeasureMemUtil==true || Config.isMeasureMemClk==true){
            
            tmpStream.clear();
            tmpStream.str("");
            tmpStream << std::endl;
            tmpStream << "-------- GPU Memory --------" << std::endl;

            if (isInit == false)
            {
                std::cout << tmpStream.str();
            }
            if(Config.isGenOutFile==true){
                outStream << tmpStream.str();
            }
        }
        if(Config.isMeasureMemUtil==true){
            avgMemUtil = sumMemUtil / TotalDuration;

            tmpStream.clear();
            tmpStream.str("");
            tmpStream << "minMemUtil: " << std::setw(6) << minMemUtil << " %; avgMemUtil: " << std::setw(6) << avgMemUtil << " %; maxMemUtil: " << std::setw(6) << maxMemUtil << " %" << std::endl;

            if (isInit == false)
            {
                std::cout << tmpStream.str();
            }
            if(Config.isGenOutFile==true){
                outStream << tmpStream.str();
            }
        }
        if(Config.isMeasureMemClk==true){
            avgMemClk= sumMemClk / TotalDuration;

            tmpStream.clear();
            tmpStream.str("");
            tmpStream << "minMemClk: " << std::setw(7) << minMemClk << " MHz; avgMemClk: " << std::setw(7) << avgMemClk << " MHz; maxMemClk: " << std::setw(7) << maxMemClk << " MHz" << std::endl;

            if (isInit == false)
            {
                std::cout << tmpStream.str();
            }
            if(Config.isGenOutFile==true){
                outStream << tmpStream.str();
            }
        }

        if(isInit == true)
        {
            // wfr 20210528 write blank lines to file
            std::string tmpStr = "                ";
            tmpStr = tmpStr + tmpStr + tmpStr + tmpStr;
            tmpStr = tmpStr + tmpStr + tmpStr + tmpStr; // 256 spaces
            for (size_t i = 0; i < NUM_APP_STAMPS + 1; i++)
            {
                outStream << tmpStr << std::endl;
            }
        }

        if(Config.isTrace == true && isInit == true){
            outStream << std::endl;
            outStream << "-------- Raw Data --------" << std::endl;
            outStream << std::endl;

            // outStream << "vecTimeStamp size: " << vecTimeStamp.size() << std::endl;
            // outStream << "vecPower size: " << vecPower.size() << std::endl;
            // outStream << "vecGPUUtil size: " << vecGPUUtil.size() << std::endl;
            // outStream << "vecSMClk size: " << vecSMClk.size() << std::endl;
            // outStream << "vecMemUtil size: " << vecMemUtil.size() << std::endl;
            // outStream << "vecMemClk size: " << vecMemClk.size() << std::endl;
            // output Power Threshold
            if(Config.isMeasureEnergy==true){
                outStream << "Power Threshold: " << std::setw(6) << Config.PowerThreshold << " W" << std::endl;
            }
            outStream << std::endl;

            // output data which were sample and their order
            outStream << "Time Stamp (s)" << std::endl;
            if(Config.isMeasureEnergy==true){
                outStream << "Power (W)" << std::endl;
            }
            if(Config.isMeasureGPUUtil==true){
                outStream << "GPUUtil (%)" << std::endl;
            }
            if(Config.isMeasureSMClk==true){
                outStream << "SMClk (MHz)" << std::endl;
            }
            if(Config.isMeasureMemUtil==true){
                outStream << "MemUtil (%)" << std::endl;
            }
            if(Config.isMeasureMemClk==true){
                outStream << "MemClk (MHz)" << std::endl;
            }
            outStream << std::endl;
        }

        return 0;
    }

    int SetOutPath(CONFIG& Config){
        if(Config.isGenOutFile==false) return 0;

        if(vecTimeStamp.capacity() < VECTOR_RESERVE){
            vecTimeStamp.reserve(VECTOR_RESERVE);
            vecPower.reserve(VECTOR_RESERVE);
            vecMemUtil.reserve(VECTOR_RESERVE);
            vecMemClk.reserve(VECTOR_RESERVE);
            vecGPUUtil.reserve(VECTOR_RESERVE);
            vecSMClk.reserve(VECTOR_RESERVE);
        }

        if(Config.isGenOutFile){
            outStream.open(Config.OutFilePath, std::ifstream::out);
            if(!outStream.is_open()){
                outStream.close();
                std::cerr << "ERROR: failed to open output file" << std::endl;
                return 1;
            }
        }

        SummaryOut(Config, true);

        return 0;
    }

    void Reset(){
        init();
        vecTimeStamp.clear();
        vecPower.clear();
        vecMemUtil.clear();
        vecMemClk.clear();
        vecGPUUtil.clear();
        vecSMClk.clear();
        vecAppStamp.clear();
        vecAppStampEnergy.clear();
        vecAppStampDescription.clear();
        outStream.close();
    }

    int init(){

        isFisrtSample = true;
        isMeasuring = 0;

        SampleCount = 0;
        TotalDuration = 0.0;
        StartTimeStamp = 0.0;
        minPower = 999; maxPower = 0; avgPower = 0.0; Energy = 0.0;
        minMemUtil = 101; maxMemUtil = 0; avgMemUtil = 0.0; sumMemUtil = 0.0;
        minMemClk = 99999; maxMemClk = 0; avgMemClk = 0.0; sumMemClk = 0.0;
        minGPUUtil = 101; maxGPUUtil = 0; avgGPUUtil = 0.0; sumGPUUtil = 0.0;
        minSMClk = 99999; maxSMClk = 0; avgSMClk = 0.0; sumSMClk = 0.0;
        prevTimeStamp.tv_sec = 0;
        prevTimeStamp.tv_usec = 0;

        return 0;
    }

    int init(CONFIG& Config){
    
        init();

        if(Config.isGenOutFile==false) return 0;

        vecTimeStamp.reserve(VECTOR_RESERVE);
        vecPower.reserve(VECTOR_RESERVE);
        vecMemUtil.reserve(VECTOR_RESERVE);
        vecMemClk.reserve(VECTOR_RESERVE);
        vecGPUUtil.reserve(VECTOR_RESERVE);
        vecSMClk.reserve(VECTOR_RESERVE);


        if(Config.isGenOutFile){
            outStream.open(Config.OutFilePath, std::ifstream::out);
            if(!outStream.is_open()){
                outStream.close();
                std::cerr << "ERROR: failed to open output file" << std::endl;
                return 1;
            }
        }

        SummaryOut(Config, true);

        // if(Config.isTrace == true){
        //     outStream << std::endl;
        //     outStream << "-------- Raw Data --------" << std::endl;
        //     outStream << std::endl;

        //     // outStream << "vecTimeStamp size: " << vecTimeStamp.size() << std::endl;
        //     // outStream << "vecPower size: " << vecPower.size() << std::endl;
        //     // outStream << "vecGPUUtil size: " << vecGPUUtil.size() << std::endl;
        //     // outStream << "vecSMClk size: " << vecSMClk.size() << std::endl;
        //     // outStream << "vecMemUtil size: " << vecMemUtil.size() << std::endl;
        //     // outStream << "vecMemClk size: " << vecMemClk.size() << std::endl;
        //     // output Power Threshold
        //     if(Config.isMeasureEnergy==true){
        //         outStream << "Power Threshold: " << Config.PowerThreshold << " W" << std::endl;
        //     }
        //     outStream << std::endl;

        //     // output data which were sample and their order
        //     outStream << "Time Stamp (s)" << std::endl;
        //     if(Config.isMeasureEnergy==true){
        //         outStream << "Power (W)" << std::endl;
        //     }
        //     if(Config.isMeasureGPUUtil==true){
        //         outStream << "GPUUtil (%)" << std::endl;
        //     }
        //     if(Config.isMeasureSMClk==true){
        //         outStream << "SMClk (MHz)" << std::endl;
        //     }
        //     if(Config.isMeasureMemUtil==true){
        //         outStream << "MemUtil (%)" << std::endl;
        //     }
        //     if(Config.isMeasureMemClk==true){
        //         outStream << "MemClk (MHz)" << std::endl;
        //     }
        //     outStream << std::endl;
        // }

        return 0;
    }

    PERF_DATA(){
        init();
    }

    PERF_DATA(CONFIG& Config){
        init(Config);
    }

    // wfr 20210528 write one piece of trace to file
    int WriteOneTrace(CONFIG& Config){

        if(Config.isTrace == true){
            double RelativeTimeStamp = (double)currTimeStamp.tv_sec + (double)currTimeStamp.tv_usec * 1e-6 - StartTimeStamp;

            // output raw data
            outStream << RelativeTimeStamp << std::endl;
            if(Config.isMeasureEnergy==true){
                outStream << ((float)currPower)/1000.0 << std::endl;
            }
            if(Config.isMeasureGPUUtil==true){
                outStream << currUtil.gpu << std::endl;
            }
            if(Config.isMeasureSMClk==true){
                outStream << currSMClk << std::endl;
            }
            if(Config.isMeasureMemUtil==true){
                outStream << currUtil.memory << std::endl;
            }
            if(Config.isMeasureMemClk==true){
                outStream << currMemClk << std::endl;
            }
            outStream << std::endl;
        }

        return 0;
    }

    // wfr 20210528 set cursor to the beginning of file and write average data and etc.
    int output(CONFIG& Config){

        // bool isOpen;

        if(Config.isGenOutFile==true){
            if(outStream.is_open()){
                // isOpen = true;
            }else{
                outStream.close();
                std::cerr << "ERROR: output file is not opened" << std::endl;
                exit(1);
            }
        }

        SummaryOut(Config, false);

        std::stringstream tmpStream;

        if(vecAppStamp.size()>0){

            tmpStream.clear();
            tmpStream.str("");
            tmpStream << std::endl;
            tmpStream << "-------- Applicaion Time Stamp --------" << std::endl;

            unsigned int tmpCount;
            if (Config.isTrace == true && vecAppStamp.size() > NUM_APP_STAMPS)
            {
                tmpStream << "# of app stamps: " << vecAppStamp.size() << ", but NUM_APP_STAMPS: " << NUM_APP_STAMPS << std::endl;
                // tmpCount = std::min((unsigned int)NUM_APP_STAMPS, (unsigned int)vecAppStamp.size());
            }
            tmpCount = vecAppStamp.size();
            
            for(unsigned int i=0; i<tmpCount; i++){
                tmpStream << vecAppStampDescription[i] << ": " << vecAppStamp[i] << " s; " << vecAppStampEnergy[i] << " J" << std::endl;
            }

            std::cout << tmpStream.str();
            if(Config.isGenOutFile==true){
                outStream << tmpStream.str();
            }
        }

        // if(Config.isGenOutFile==true){
        //     if(Config.isTrace == true){
        //         std::cout << std::endl;
        //         std::cout << "Write raw data to file..." << std::endl;
        //         std::cout << std::endl;
        //     }else{
        //         outStream.close();
        //         return 0;
        //     }
        // }else{
        //     return 0;
        // }

        outStream.close();

        return 0;
    }
};


#endif