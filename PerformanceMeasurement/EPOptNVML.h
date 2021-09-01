/*******************************************************************************
Copyright(C), 2020-2021, 瑞雪轻飏
     FileName: EPOptNVML.h
       Author: 瑞雪轻飏
      Version: 0.01
Creation Date: 20210719
  Description: 1. 为了降低开销, NVML不用时就立刻关闭; EPOPT_NVML类中加入使用计数,
                当使用计数为0, 就关闭, 否则认为还在使用
               2. 每次调用 NMVL API 前, 先调用 EPOPT_NVML::Init, 使用计数++
               3. 每次调用 NMVL API 后, 调用 EPOPT_NVML::Unnit, 使用计数--
       Others: //其他内容说明
*******************************************************************************/

#ifndef __EPOPT_NVML_H
#define __EPOPT_NVML_H

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

class EPOPT_NVML{
public:
    int UsageCount;
    pthread_mutex_t mutexNVML; // wfr 20210715 mutex for CUPTI
    // pthread_cond_t condNVML; // wfr 20210715 cond for CUPTI

    nvmlReturn_t nvmlResult;

    int Init(){
        pthread_mutex_lock(&mutexNVML);
        if (UsageCount == 0)
        {
            nvmlResult = nvmlInit();
            if (NVML_SUCCESS != nvmlResult)
            {
                std::cout << "EPOPT_NVML::Init: Failed to init NVML (NVML ERROR INFO: " << nvmlErrorString(nvmlResult) << ")." << std::endl;
                exit(-1);
            }
        }
        UsageCount++;
        pthread_mutex_unlock(&mutexNVML);
        return 0;
    }
    
    int Uninit(){
        pthread_mutex_lock(&mutexNVML);
        if (UsageCount > 0)
        {
            UsageCount--;
            if (UsageCount == 0)
            {
                nvmlResult = nvmlShutdown();
                if (NVML_SUCCESS != nvmlResult)
                {
                    std::cout << "EPOPT_NVML::Init: Failed to nvmlShutdown NVML (NVML ERROR INFO: " << nvmlErrorString(nvmlResult) << ")." << std::endl;
                    exit(-1);
                }
            }
        }
        pthread_mutex_unlock(&mutexNVML);
        return 0;
    }

    EPOPT_NVML(){
        pthread_mutex_init(&mutexNVML, NULL);
        pthread_mutex_unlock(&mutexNVML);
        UsageCount = 0;
    }
    ~EPOPT_NVML(){
        nvmlResult = nvmlShutdown();
        UsageCount = 0;
    }
};

#endif