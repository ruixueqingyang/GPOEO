/*******************************************************************************
Copyright(C), 2020-2020, 瑞雪轻飏
     FileName: MsgEPRT.h
       Author: 瑞雪轻飏
      Version: 0.01
Creation Date: 20200704
  Description: 向运行时发送信息
       Others: //其他内容说明
*******************************************************************************/

#ifndef __MSG_EPRT_H
#define __MSG_EPRT_H

#include <stdio.h>
#include <stdlib.h>
#include <iostream>
#include <vector>
#include <system_error>
#include <string>
#include <vector>
#include <assert.h>
#include <math.h>
#include <fstream>
#include <memory.h>

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

#define BUFF_LEN 128
#define SERVER_PORT 7777

int SetSMClkRange(float LowerPercent, float UpperPercent);
int ResetSMClk();
int TimeStamp(std::string& Description);
int StartMeasurement();
int StopMeasurement();
int ExitMeasurement();
int ResetMeasurement();
int ResetMeasurement(std::string& OutPath);

#endif