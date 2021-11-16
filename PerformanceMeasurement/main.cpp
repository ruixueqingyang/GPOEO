/*******************************************************************************
Copyright(C), 2020-2021, 瑞雪轻飏
     FileName: main.cpp
       Author: 瑞雪轻飏
      Version: 0.1
Creation Date: 20200504
  Description: 性能/能耗测量工具的主/入口 cpp 文件, 包含 main 函数
       Others: 
*******************************************************************************/

#include "main.h"

CONFIG Config;
PERF_DATA PerfData;
EPOPT_NVML MyNVML;
POWER_MANAGER PM(&MyNVML);

// pthread_create() 中 传递给新线程的 参数
std::vector<unsigned int> vecAppIndex;
void* Argv[NUM_BUFFS][3];

int ParseOptions(int argc, char** argv, bool& isTuneAtBegin);
int MeasureInit();
void AlarmSampler(int signum);
static void* ForkChildProcess(void* arg);
void HandleUDPMsg(int fd);
static void* HandleAppMsg(void* ppArgs);

// 主函数
int main(int argc, char** argv){
    int err;
    char CharBuffer[6];
    std::string tmpString;
    const std::string stop = "stop";
    const std::string Stop = "Stop";
    const std::string STOP = "STOP";

    // 处理输入参数
    // Parse input arguments
    bool isTuneAtBegin = false;
    err = ParseOptions(argc, argv, isTuneAtBegin);
    if( 0 != err ) exit(err);

    err = MeasureInit();
    if( 0 != err ) exit(err);

    if (isTuneAtBegin == true)
    {
        // PM.Set();
    }
    
    if(Config.MeasureMode==MEASURE_MODE::DAEMON){

        // 初始化 socket
        int server_fd, ret;
        struct sockaddr_in ser_addr;

        server_fd = socket(AF_INET, SOCK_DGRAM, 0); //AF_INET:IPV4;SOCK_DGRAM:UDP
        if(server_fd < 0)
        {
            printf("create socket fail!\n");
            return -1;
        }

        memset(&ser_addr, 0, sizeof(ser_addr));
        ser_addr.sin_family = AF_INET;
        ser_addr.sin_addr.s_addr = htonl(INADDR_ANY); //IP地址，需要进行网络序转换，INADDR_ANY：本地地址
        ser_addr.sin_port = htons(SERVER_PORT);  //端口号，需要网络序转换

        ret = bind(server_fd, (struct sockaddr*)&ser_addr, sizeof(ser_addr));
        if(ret < 0)
        {
            std::cout << "socket bind fail! (err_code = " << ret << ")" << std::endl;
            return -1;
        }

        //忽略子进程停止或退出信号
        // signal(SIGCHLD, SIG_IGN);

        HandleUDPMsg(server_fd);   //处理接收到的数据

        close(server_fd);

        // output result
        // PerfData.output(Config);

    }else if(Config.MeasureMode==MEASURE_MODE::INTERACTION){

        // 注册时钟信号，启动采样
        signal(SIGALRM, AlarmSampler);
        struct itimerval tick;
        tick.it_value.tv_sec = 0; //0秒钟后将启动定时器
        tick.it_value.tv_usec = 1;
        tick.it_interval.tv_sec = 0; //定时器启动后，每隔 Config.SampleInterval*1000 us 将执行相应的函数
        tick.it_interval.tv_usec = Config.SampleInterval*1000;
        setitimer(ITIMER_REAL, &tick, NULL);
        // ualarm(10, Config.SampleInterval*1000);

        std::cout << "Sampling has already started." << std::endl;
        std::cout << "Sampling..." << std::endl;
        std::cout << "Type \"stop\" to stop sampling: ";

        while(true){
            std::cin.getline(CharBuffer, 5);
            CharBuffer[5] = '\0';
            tmpString = CharBuffer;
            // std::getline(std::cin, tmpString);
            if( tmpString==stop || tmpString==Stop || tmpString==STOP){
                struct itimerval tick;
                getitimer(ITIMER_REAL, &tick); // 获得本次定时的剩余时间
                tick.it_interval.tv_sec = 0; // 设置 interval 为0，完成本次定时之后，停止定时
                tick.it_interval.tv_usec = 0;
                setitimer(ITIMER_REAL, &tick, NULL); // 完成本次定时之后，停止定时
                // ualarm(0, Config.SampleInterval*1000);
                std::cout << "Sampling has already stopped." << std::endl;
                break;
            }else{
                std::cout << "Sampling..." << std::endl;
                std::cout << "Type \"stop\" to stop sampling: ";
            }
            memset(CharBuffer, 0, 6);
        }
        // output result
        PerfData.output(Config);
    }else if(Config.MeasureMode==MEASURE_MODE::APPLICATION){

        std::vector<pthread_t> vecAppTID;
        vecAppTID.reserve(Config.vecAppPath.size());
        vecAppIndex.reserve(Config.vecAppPath.size());
        // int count = 0;
        pthread_attr_t attr;

        // 初始化条件变量 初值为 0
        pthread_mutex_init(&mutexTStart, NULL);
        pthread_cond_init(&condTStart, NULL);
        // pthread_mutex_lock(&mutexTStart);

        ChlidFinishCount = 0;
        ChlidWaitCount = 0;
        pthread_mutex_init(&mutexTEnd, NULL);
        pthread_cond_init(&condTEnd, NULL);

        pthread_attr_init(&attr);
        pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_JOINABLE);

        // fork 所需的所有子线程, 并检查是否出错, 并记录子线程 tid
        for(unsigned int i = 0; i<Config.vecAppPath.size(); i++){
            vecAppIndex[i] = i;
            err = pthread_create(&vecAppTID[i], &attr, ForkChildProcess, (void*)&vecAppIndex[i]);
            if(err != 0) {
                std::cerr << "ERROR: pthread_create() return code: " << err << std::endl;
                return -1;
            }
        }

        while(ChlidWaitCount != Config.vecAppPath.size()){
            usleep(10000);
        }

        // 注册时钟信号，启动采样
        signal(SIGALRM, AlarmSampler);
        struct itimerval tick;
        tick.it_value.tv_sec = 0; //0秒钟后将启动定时器
        tick.it_value.tv_usec = 1;
        tick.it_interval.tv_sec = 0; //定时器启动后，每隔 Config.SampleInterval*1000 us 将执行相应的函数
        tick.it_interval.tv_usec = Config.SampleInterval*1000;
        setitimer(ITIMER_REAL, &tick, NULL);
        // ualarm(10, Config.SampleInterval*1000);

        std::cout << "Sampling has already started." << std::endl;
        std::cout << "Sampling..." << std::endl;

        // 启动子线程, 创建应用进程
        pthread_cond_broadcast(&condTStart);
        pthread_mutex_unlock(&mutexTStart);

        while(true){
            pthread_mutex_lock(&mutexTEnd);

            pthread_cond_wait(&condTEnd, &mutexTEnd); // 这里会先解锁 mutexTEnd, 然后阻塞, 返回后再上锁 mutexTEnd

            // 如果所有子线程都完成了, 即所有应用都执行完了
            if(ChlidFinishCount == Config.vecAppPath.size()){
                pthread_mutex_unlock(&mutexTEnd); // 为了上锁/解锁配对, 加上这句
                break;
            }

            pthread_mutex_unlock(&mutexTEnd);
        }

        // 结束采样
        // struct itimerval tick;
        getitimer(ITIMER_REAL, &tick); // 获得本次定时的剩余时间
        tick.it_interval.tv_sec = 0; // 设置 interval 为0，完成本次定时之后，停止定时
        tick.it_interval.tv_usec = 0;
        setitimer(ITIMER_REAL, &tick, NULL); // 完成本次定时之后，停止定时
        // ualarm(0, Config.SampleInterval*1000);
        std::cout << "Sampling has already stopped." << std::endl;
        
        for (unsigned int i = 0; i<Config.vecAppPath.size(); i++) {
            pthread_join(vecAppTID[i], NULL);
        } 
        
        // 清理 并 退出
        pthread_attr_destroy(&attr);
        pthread_mutex_destroy(&mutexTStart);
        pthread_mutex_destroy(&mutexTEnd);
        pthread_cond_destroy(&condTStart);
        pthread_cond_destroy(&condTEnd);
        // pthread_exit(NULL);

        // output result
        PerfData.output(Config);
        
    }else{
        std::cerr << "Illegal measurement mode !" << std::endl;
    }
    
    PM.Reset();
    MyNVML.Uninit();
    
    return 0;
}

void HandleUDPMsg(int fd){

    bool arrayValidFlag[NUM_BUFFS]; // 表示缓冲区是否可用
    char buf[NUM_BUFFS][BUFF_LEN]; // 接收缓冲区，1024字节
    
    socklen_t SizeofSockAddr;
    int MsgLen;
    struct sockaddr_in client_addr;  //clent_addr用于记录发送方的地址信息
    
    pthread_mutex_init(&lockValidFlag, NULL);
    pthread_mutex_init(&lockMsgHandlerSource, NULL);
    pthread_mutex_unlock(&lockValidFlag);
    pthread_mutex_unlock(&lockMsgHandlerSource);

    // std::vector< pthread_t > vecTID(0, NUM_BUFFS);
    pthread_t arrayTID[NUM_BUFFS];

    pthread_mutex_lock(&lockValidFlag);
    for(unsigned int i=0; i<NUM_BUFFS; i++){
        arrayValidFlag[i] = true;
        arrayTID[i] = 0;
        memset(buf[i], 0, BUFF_LEN);
    }
    pthread_mutex_unlock(&lockValidFlag);

    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);

    // while 循环，处理 外部请求：开始测量，结束测量，调节频率，调节功率上限 等
    // 每个请求 单独启动 一个 线程/进程 进行处理
    while(true){

        // std::cout << "DEBUG: 执行 pthread_mutex_lock(&lockValidFlag)" << std::endl;
        pthread_mutex_lock(&lockValidFlag);
        int BufIndex=0;
        for(; BufIndex<NUM_BUFFS; BufIndex++){
            // std::cout << "DEBUG: BufIndex = " << BufIndex << std::endl;
            if( arrayValidFlag[BufIndex] == true ){
                break;
            }
        }
        pthread_mutex_unlock(&lockValidFlag);

        if(BufIndex>=NUM_BUFFS){
            std::cout << "WARNING: buffer queue is full, cannot handle new UDP message!" << std::endl;
            usleep(1000); // 暂停 1 ms
            exit(-1);
            continue;
        }

        SizeofSockAddr = sizeof(client_addr);
        // std::cout << "DEBUG: 执行 recvfrom" << std::endl;
        MsgLen = recvfrom(fd, buf[BufIndex], BUFF_LEN, 0, (struct sockaddr*)&client_addr, &SizeofSockAddr);  //recvfrom是拥塞函数，没有数据就一直拥塞
        if(MsgLen == -1){
            std::cout << "WARNING: recieve data fail!" << std::endl;
            memset(buf[BufIndex], 0, BUFF_LEN);
            continue;
        }else{
            std::cout << "DEBUG: BufIndex = " << BufIndex << "; UDP receive buffer: " << buf[BufIndex] << std::endl;
        }

        
        if(strncmp(buf[BufIndex], "EXIT", 4) == 0){ // 如果 UDP 信息是 EXIT 就跳出
            memset(buf[BufIndex], 0, BUFF_LEN);
            int tmpMeasuring;
            for(unsigned int i=0; i<5; i++){
                pthread_mutex_lock(&lockMsgHandlerSource);
                tmpMeasuring = PerfData.isMeasuring;
                pthread_mutex_unlock(&lockMsgHandlerSource);
                if(tmpMeasuring>0){
                    std::cout << "WARNING: Sampling in progress!" << std::endl;
                    usleep(5*1000*Config.SampleInterval); // 这里循环等待 一共 5*5 个采样周期
                }else{
                    break;
                }
            }
            if(tmpMeasuring>0){
                std::cout << "WARNING: Sampling in progress, but forced to exit!" << std::endl;
            }else{
                std::cout << "INFO: Measurement exit" << std::endl;
            }
            break;
        }

        arrayValidFlag[BufIndex] = false;
        
        Argv[BufIndex][0] = (void*)BufIndex;
        Argv[BufIndex][1] = (void*)&arrayValidFlag[BufIndex];
        Argv[BufIndex][2] = (void*)buf[BufIndex];

        int err = pthread_create(&arrayTID[BufIndex], &attr, HandleAppMsg, (void*)Argv[BufIndex]);
        if(err != 0) {
            std::cerr << "ERROR: pthread_create() return code: " << err << std::endl;
            arrayValidFlag[BufIndex] = true;
            memset(buf[BufIndex], 0, BUFF_LEN);
            continue;
        }

    }

}

static void* HandleAppMsg(void* Argv){

    int BufIndex = ((char*)Argv)[0];
    bool* pValidFlag = ((bool**)Argv)[1];
    char* buf = ((char**)Argv)[2];
    std::string tmpStr = buf;
    memset(buf, 0, BUFF_LEN);
    
    std::cout << "INFO: BufIndex = " << BufIndex << "; 收到 Msg tmpStr = " << tmpStr << std::endl;

    tmpStr.erase(0, tmpStr.find_first_not_of(" \t\r\n"));
    tmpStr.erase(tmpStr.find_last_not_of(" \t\r\n") + 1);

    if(tmpStr.find("TIME_STAMP: ")==0){ // 时间戳
        pthread_mutex_lock(&lockMsgHandlerSource);
        std::cout << "INFO: 处理 TIME_STAMP 信号 isMeasuring = " << PerfData.isMeasuring << std::endl;
        if(PerfData.isMeasuring<0){
            std::cout << "WARNING: measurement count < 0 (isMeasuring = " << PerfData.isMeasuring << ")" << std::endl;
        }else if(PerfData.isMeasuring==0){
            std::cout << "WARNING: measurement not started (isMeasuring = " << PerfData.isMeasuring << ")" << std::endl;
        }else{
            PerfData.vecAppStampDescription.emplace_back(tmpStr.substr(strlen("TIME_STAMP: ")));
            std::cout << "INFO: save time stamp description (" << tmpStr << ")" << std::endl;
        }
        pthread_mutex_unlock(&lockMsgHandlerSource);
        
    }else if(tmpStr.find("SM_RANGE: ")==0){ // 调节核心频率范围
        std::size_t pos1 = tmpStr.find_first_of(".0123456789"); // 找到第一个数字的起始位置
        std::size_t pos2 = tmpStr.find_first_of(",", pos1+1);
        pos2 = tmpStr.find_first_of(".0123456789", pos2+1); // 找到第二个数字的起始位置

        std::string LowerBoundStr = tmpStr.substr(pos1);
        std::string UpperBoundStr = tmpStr.substr(pos2);

        int LowerBound = stoi(LowerBoundStr);
        int UpperBound = stoi(UpperBoundStr);

        PM.SetSMClkRange(LowerBound, UpperBound);

    }else if(tmpStr.find("SM_RANGE_PCT: ")==0){ // 调节核心频率范围
        std::size_t pos1 = tmpStr.find_first_of(".0123456789"); // 找到第一个数字的起始位置
        std::size_t pos2 = tmpStr.find_first_of(",", pos1+1);
        pos2 = tmpStr.find_first_of(".0123456789", pos2+1); // 找到第二个数字的起始位置

        std::string LowerBoundStr = tmpStr.substr(pos1);
        std::string UpperBoundStr = tmpStr.substr(pos2);

        float LowerBound = stof(LowerBoundStr)/100;
        float UpperBound = stof(UpperBoundStr)/100;

        PM.SetSMClkRange(LowerBound, UpperBound);

    }else if(tmpStr.find("RESET_SM_CLOCK")==0){ // 重置核心频率范围
        PM.Reset();

    }else if(tmpStr.find("START")==0){ // 开始测量
        pthread_mutex_lock(&lockMsgHandlerSource);
        if(PerfData.isMeasuring<0){
            pthread_mutex_unlock(&lockMsgHandlerSource);
            std::cout << "WARNING: measurement count < 0 (isMeasuring = " << PerfData.isMeasuring << ")" << std::endl;
        }else if(PerfData.isMeasuring==0){
            PerfData.isMeasuring++; // 启动计数++
            std::cout << "INFO: 处理 START 信号 isMeasuring = " << PerfData.isMeasuring << std::endl;
            pthread_mutex_unlock(&lockMsgHandlerSource);
            // 注册时钟信号，启动采样
            signal(SIGALRM, AlarmSampler);
            struct itimerval tick;
            tick.it_value.tv_sec = 0; //0秒钟后将启动定时器
            tick.it_value.tv_usec = 1;
            tick.it_interval.tv_sec = 0; //定时器启动后，每隔 Config.SampleInterval*1000 us 将执行相应的函数
            tick.it_interval.tv_usec = Config.SampleInterval*1000;
            setitimer(ITIMER_REAL, &tick, NULL);
            // ualarm(10, Config.SampleInterval*1000);
            std::cout << "Sampling has already started." << std::endl;
            std::cout << "Sampling..." << std::endl;
        }
        // PerfData.isMeasuring++; // 启动计数++
        // std::cout << "INFO: 处理 START 信号 isMeasuring = " << PerfData.isMeasuring << std::endl;
        // pthread_mutex_unlock(&lockMsgHandlerSource);

    }else if(tmpStr.find("STOP")==0){ // 结束测量
        usleep(0.2*1000*1000); // 暂停 0.2s ，使所有时间戳都被记录下来。
        std::cout << "INFO: 处理 STOP 信号 开始获得锁 lockMsgHandlerSource " << std::endl;
        pthread_mutex_lock(&lockMsgHandlerSource);
        std::cout << "INFO: 处理 STOP 信号 已经获得锁 lockMsgHandlerSource " << std::endl;
        PerfData.isMeasuring--; // 启动计数--
        std::cout << "INFO: 处理 STOP 信号 isMeasuring = " << PerfData.isMeasuring << std::endl;
        if(PerfData.isMeasuring<0){
            pthread_mutex_unlock(&lockMsgHandlerSource);
            std::cout << "WARNING: measurement count < 0 (isMeasuring = " << PerfData.isMeasuring << ")" << std::endl;
        }else if(PerfData.isMeasuring==0){
            pthread_mutex_unlock(&lockMsgHandlerSource);
            // 结束采样
            struct itimerval tick;
            getitimer(ITIMER_REAL, &tick); // 获得本次定时的剩余时间
            tick.it_interval.tv_sec = 0; // 设置 interval 为0，完成本次定时之后，停止定时
            tick.it_interval.tv_usec = 0;
            setitimer(ITIMER_REAL, &tick, NULL); // 完成本次定时之后，停止定时
            // ualarm(0, Config.SampleInterval*1000);
            usleep(20*1000); // 暂停 20ms ，使所有时间戳都被记录下来。
            std::cout << "Sampling has already stopped." << std::endl;
            PerfData.output(Config);

            Config.Reset();
            PerfData.Reset();
        }
        
        
    }else if(tmpStr.find("RESET")==0){
        unsigned int WaitNum = 10;
        unsigned int Len = 7;
        for(unsigned int i=0; i<WaitNum; i++){
            pthread_mutex_lock(&lockMsgHandlerSource);
            std::cout << "INFO: 处理 RESET 信号 isMeasuring = " << PerfData.isMeasuring << std::endl;
            if(PerfData.isMeasuring>0){
                pthread_mutex_unlock(&lockMsgHandlerSource);
                if(i == (WaitNum-1)){
                    std::cout << "WARNING: Sampling is still in progress! NOT RESET!" << std::endl;
                }else{
                    std::cout << "WARNING: Sampling is in progress! Wait 1s" << std::endl;
                    sleep(1); // 这里循环等待 1s * (WaitNum-1)，每秒监测一次
                }
                continue;
            }else{
                if(tmpStr.size()>Len){
                    std::string OutPath = tmpStr.substr(Len);
                    Config.Reset(OutPath);
                    PerfData.Reset();
                    PerfData.SetOutPath(Config);
                }else{
                    Config.Reset();
                    PerfData.Reset();
                }
                
                pthread_mutex_unlock(&lockMsgHandlerSource);
                break;
            }

        }
    }else{}

    pthread_mutex_lock(&lockValidFlag);
    *pValidFlag = true;
    // memset(buf, 0, BUFF_LEN);
    pthread_mutex_unlock(&lockValidFlag);

    std::cout << "INFO: BufIndex = " << BufIndex << "; 退出线程" << std::endl;

    pthread_exit(NULL);
}

static void* ForkChildProcess(void* arg){

    pid_t AppPid;
    int PStatus;

    unsigned int* pAppIndex = (unsigned int*)arg;

    pthread_mutex_lock(&mutexTStart);
    ChlidWaitCount++;
    pthread_cond_wait(&condTStart, &mutexTStart);
    pthread_mutex_unlock(&mutexTStart);

    AppPid = fork();
    if(AppPid == 0){ // 子进程

        std::cout << "Application " << *pAppIndex + 1 << " is being launched..." << std::endl;

        char *ptmp_3char = Config.vecAppPath[*pAppIndex] + strlen(Config.vecAppPath[*pAppIndex]) - 3;
        if(strncmp(ptmp_3char, ".sh", 3)==0){
            execl("/bin/bash", "/bin/bash", Config.vecAppPath[*pAppIndex], NULL);
            printf("ERROR: execl on application %s failed\n", Config.vecAppPath[0]);
        }else{
            execv(Config.vecAppPath[*pAppIndex], Config.vecAppAgrv[*pAppIndex]);
            printf("ERROR: execv on application %s failed\n", Config.vecAppPath[0]);
        }
        exit(-1);

    }else if(AppPid < 0){ // 主进程 fork 出错
        std::cerr << "ERROR: fork on application " << *pAppIndex + 1 << " failed" << std::endl;
        exit(-1);
    }

    // 主进程
    waitpid(AppPid,&PStatus,0); // 等待应用所在进程运行结束
    
    pthread_mutex_lock(&mutexTEnd);
    std::cout << "Application " << *pAppIndex + 1 << " has finished" << std::endl;
    ChlidFinishCount++; // 应用完成计数 ++
    pthread_cond_signal(&condTEnd); // 通知主线程, 一个应用已经执行完成
    pthread_mutex_unlock(&mutexTEnd);

    pthread_exit(NULL);
}

void AlarmSampler(int signum){

    // std::cout << "INFO: 进入 AlarmSampler" << std::endl;

    if(signum != SIGALRM) return;

    nvmlReturn_t nvmlResult;

    gettimeofday(&PerfData.currTimeStamp,NULL);

    // get current value
    if(Config.isMeasureEnergy==true){
        nvmlResult = nvmlDeviceGetPowerUsage(PerfData.nvmlDevice, &PerfData.currPower);
        if (NVML_SUCCESS != nvmlResult) {
            printf("Failed to get power usage: %s\n", nvmlErrorString(nvmlResult));
            exit(-1);
        }
    }
    

    if(Config.isMeasureSMClk==true){
        nvmlResult = nvmlDeviceGetClockInfo(PerfData.nvmlDevice, NVML_CLOCK_SM, &PerfData.currSMClk);
        if (NVML_SUCCESS != nvmlResult) {
            printf("Failed to get SM clock: %s\n", nvmlErrorString(nvmlResult));
            exit(-1);
        }
    }

    if(Config.isMeasureMemClk==true){
        nvmlResult = nvmlDeviceGetClockInfo(PerfData.nvmlDevice, NVML_CLOCK_MEM, &PerfData.currMemClk);
        if (NVML_SUCCESS != nvmlResult) {
            printf("Failed to get memory clock: %s\n", nvmlErrorString(nvmlResult));
            exit(-1);
        }
    }
    

    if(Config.isMeasureMemUtil==true || Config.isMeasureGPUUtil==true){
        nvmlResult = nvmlDeviceGetUtilizationRates(PerfData.nvmlDevice, &PerfData.currUtil);
        if (NVML_SUCCESS != nvmlResult) {
            printf("Failed to get utilization rate: %s\n", nvmlErrorString(nvmlResult));
            exit(-1);
        }
    }

    // update SampleCount
    PerfData.SampleCount++;

    // update min/max and push data
    if(Config.isMeasureEnergy==true){
        if(PerfData.currPower < PerfData.minPower){
            PerfData.minPower = PerfData.currPower;
        }
        if(PerfData.currPower > PerfData.maxPower){
            PerfData.maxPower = PerfData.currPower;
        }
        // if(Config.isGenOutFile==true && Config.isTrace == true){
        //     PerfData.vecPower.push_back(PerfData.currPower);
        // }
    }

    if(Config.isMeasureSMClk==true){
        if(PerfData.currSMClk < PerfData.minSMClk){
            PerfData.minSMClk = PerfData.currSMClk;
        }
        if(PerfData.currSMClk > PerfData.maxSMClk){
            PerfData.maxSMClk = PerfData.currSMClk;
        }
        // if(Config.isGenOutFile==true && Config.isTrace == true){
        //     PerfData.vecSMClk.push_back(PerfData.currSMClk);
        // }
    }

    if(Config.isMeasureMemClk==true){
        if(PerfData.currMemClk < PerfData.minMemClk){
            PerfData.minMemClk = PerfData.currMemClk;
        }
        if(PerfData.currMemClk > PerfData.maxMemClk){
            PerfData.maxMemClk = PerfData.currMemClk;
        }
        // if(Config.isGenOutFile==true && Config.isTrace == true){
        //     PerfData.vecMemClk.push_back(PerfData.currMemClk);
        // }
    }

    if(Config.isMeasureMemUtil==true){
        if(PerfData.currUtil.memory < PerfData.minMemUtil){
            PerfData.minMemUtil = PerfData.currUtil.memory;
        }
        if(PerfData.currUtil.memory > PerfData.maxMemUtil){
            PerfData.maxMemUtil = PerfData.currUtil.memory;
        }
        // if(Config.isGenOutFile==true && Config.isTrace == true){
        //     PerfData.vecMemUtil.push_back(PerfData.currUtil.memory);
        // }
    }

    if(Config.isMeasureGPUUtil==true){
        if(PerfData.currUtil.gpu < PerfData.minGPUUtil){
            PerfData.minGPUUtil = PerfData.currUtil.gpu;
        }
        if(PerfData.currUtil.gpu > PerfData.maxGPUUtil){
            PerfData.maxGPUUtil = PerfData.currUtil.gpu;
        }
        // if(Config.isGenOutFile==true && Config.isTrace == true){
        //     PerfData.vecGPUUtil.push_back(PerfData.currUtil.gpu);
        // }
    }

    // calculate ActualInterval/sum value, and push timestamp
    if(PerfData.isFisrtSample==true){
        PerfData.isFisrtSample = false;

        PerfData.StartTimeStamp = (double)PerfData.currTimeStamp.tv_sec + (double)PerfData.currTimeStamp.tv_usec * 1e-6;

        // if(Config.isGenOutFile==true && Config.isTrace == true){
        //     PerfData.vecTimeStamp.clear();
        //     PerfData.vecTimeStamp.push_back(0.0);
        // }

    }else{
        double ActualInterval; // (s)
        double RelativeTimeStamp; // (s)

        ActualInterval = (double)(PerfData.currTimeStamp.tv_sec - PerfData.prevTimeStamp.tv_sec) + (double)(PerfData.currTimeStamp.tv_usec - PerfData.prevTimeStamp.tv_usec) * 1e-6;

        RelativeTimeStamp = (double)PerfData.currTimeStamp.tv_sec + (double)PerfData.currTimeStamp.tv_usec * 1e-6 - PerfData.StartTimeStamp;

        PerfData.TotalDuration = RelativeTimeStamp;

        // if(Config.isGenOutFile==true && Config.isTrace == true){
        //     PerfData.vecTimeStamp.push_back(RelativeTimeStamp);
        // }
        if(Config.isMeasureEnergy==true){
            PerfData.Energy += (float)(PerfData.prevPower + PerfData.currPower) / 2 * ActualInterval;
        }
        if(Config.isMeasureSMClk==true){
            PerfData.sumSMClk += (float)(PerfData.prevSMClk + PerfData.currSMClk) / 2 * ActualInterval;
        }
        if(Config.isMeasureMemClk==true){
            PerfData.sumMemClk += (float)(PerfData.prevMemClk + PerfData.currMemClk) / 2 * ActualInterval;
        }
        if(Config.isMeasureMemUtil==true){
            PerfData.sumMemUtil += (float)(PerfData.prevUtil.memory + PerfData.currUtil.memory) / 2 * ActualInterval;
        }
        if(Config.isMeasureGPUUtil==true){
            PerfData.sumGPUUtil += (float)(PerfData.prevUtil.gpu + PerfData.currUtil.gpu) / 2 * ActualInterval;
        }
    }

    // wfr 20210528 write one piece of trace to file
    PerfData.WriteOneTrace(Config);

    // update previous value
    PerfData.prevTimeStamp.tv_sec = PerfData.currTimeStamp.tv_sec;
    PerfData.prevTimeStamp.tv_usec = PerfData.currTimeStamp.tv_usec;
    PerfData.prevUtil.memory = PerfData.currUtil.memory;
    PerfData.prevUtil.gpu = PerfData.currUtil.gpu;
    PerfData.prevPower = PerfData.currPower;
    PerfData.prevMemClk = PerfData.currMemClk;
    PerfData.prevSMClk = PerfData.currSMClk;

    // write time stamp
    if(Config.isGenOutFile==true){
        pthread_mutex_lock(&lockMsgHandlerSource);
        
        unsigned int NumStamps = PerfData.vecAppStampDescription.size()-PerfData.vecAppStamp.size();
        if(NumStamps>0){
            std::vector<double>::iterator iterAppStamp = PerfData.vecAppStamp.end();
            std::vector<double>::iterator iterAppStampEnergy = PerfData.vecAppStampEnergy.end();

            float EnergyAbove = PerfData.Energy/1000 - Config.PowerThreshold*PerfData.TotalDuration;
            float Energy = PerfData.Energy/1000;
            PerfData.vecAppStamp.insert(iterAppStamp, NumStamps, PerfData.TotalDuration);
            PerfData.vecAppStampEnergy.insert(iterAppStampEnergy, NumStamps, Energy);
            std::cout << "INFO: save " << NumStamps << " time stamp" << std::endl;
        }
        pthread_mutex_unlock(&lockMsgHandlerSource);
    }
    
}

int MeasureInit(){
    CUresult cuResult;
    cudaError_t cuError;
    nvmlReturn_t nvmlResult;
	int DeviceCount;
    //int a;

    PerfData.init(Config);

    cuResult = cuInit(0);
    if (cuResult != CUDA_SUCCESS) {
        printf("Error code %d on cuInit\n", cuResult);
        exit(-1);
    }

    cuError = cudaGetDeviceCount(&DeviceCount);
    if (cuError != cudaSuccess) {
        printf("Error code %d on cudaGetDeviceCount\n", cuResult);
        exit(-1);
    }

    printf("Found %d device%s\n\n", DeviceCount, DeviceCount != 1 ? "s" : "");
    if (Config.DeviceID >= DeviceCount) {
        printf("DeviceID is out of range.\n");
        return -1;
    }

    cuResult = cuDeviceGet(&PerfData.cuDevice, Config.DeviceID);
    if (cuResult != CUDA_SUCCESS) {
        printf("Error code %d on cuDeviceGet\n", cuResult);
        exit(-1);
    }

    cuResult = cuDeviceGetAttribute (&PerfData.ComputeCapablityMajor, CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MAJOR, PerfData.cuDevice);
    if (cuResult != CUDA_SUCCESS) {
        printf("Error code %d on cuDeviceGetAttribute\n", cuResult);
        exit(-1);
    }
    cuResult = cuDeviceGetAttribute (&PerfData.ComputeCapablityMinor, CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MINOR, PerfData.cuDevice);
    if (cuResult != CUDA_SUCCESS) {
        printf("Error code %d on cuDeviceGetAttribute\n", cuResult);
        exit(-1);
    }

	// NVML INITIALIZATIONS
    MyNVML.Init();

	nvmlResult = nvmlDeviceGetHandleByIndex(Config.DeviceID, &PerfData.nvmlDevice);
	if (NVML_SUCCESS != nvmlResult)
	{
		printf("Failed to get handle for device 1: %s\n", nvmlErrorString(nvmlResult));
		 return -1;
	}

	return 0;
}

int ParseOptions(int argc, char** argv, bool& isTuneAtBegin){
    
    int err = 0;
    isTuneAtBegin = false;
    unsigned int indexArg = 1; // 当前 flag(即-xxxx) 在 argv 中的 index
    extern int optind,opterr,optopt;
    extern char *optarg;
    const char usage[] = "Usage: %s [-e] \nType '??? -h' for help.\n";

    Config.init();
    PM.init(&MyNVML);

    //定义长选项
    static struct option long_options[] = 
    {
        {"h", no_argument, NULL, 'h'},
        {"help", no_argument, NULL, 'h'},

        {"m", required_argument, NULL, 'm'},
        {"mode", required_argument, NULL, 'm'},

        // {"d", required_argument, NULL, 'd'},
        // {"duration", required_argument, NULL, 'd'},
        {"a", required_argument, NULL, 'a'},
        {"app", required_argument, NULL, 'a'},
        {"l", required_argument, NULL, 'l'},
        {"applistfile", required_argument, NULL, 'l'},
        {"p", required_argument, NULL, 'p'},
        {"postinterval", required_argument, NULL, 'p'},
        
        {"o", required_argument, NULL, 'o'},
        {"outfile", required_argument, NULL, 'o'},

        {"i", required_argument, NULL, 'i'},
        {"id", required_argument, NULL, 'i'},
        {"s", required_argument, NULL, 's'},
        {"samplinginterval", required_argument, NULL, 's'},
        {"t", required_argument, NULL, 't'},
        {"threshold", required_argument, NULL, 't'},

        {"e", no_argument, NULL, 'e'},
        {"energy", no_argument, NULL, 'e'},
        {"memuti", no_argument, NULL, 1},
        {"memclk", no_argument, NULL, 2},
        {"gpuuti", no_argument, NULL, 3},
        {"smclk", no_argument, NULL, 4},

        {"tune", required_argument, NULL, 0},
        {"tunearg", required_argument, NULL, 5},
        {"lower", required_argument, NULL, 6},
        {"upper", required_argument, NULL, 7},

        {"trace", no_argument, NULL, 8}
    };

    int aSet=0, lSet=0, pSet=0, oSet=0, iSet=0, sSet=0, tSet=0, eSet=0, memutiSet=0, memclkSet=0, gpuutiSet=0, smclkSet=0, tuneSet=0, tuneargSet=0, lowerSet=0, upperSet=0, mSet=0, traceSet=0;

    int c = 0; //用于接收选项
    /*循环处理参数*/
    while(EOF != (c = getopt_long_only(argc, argv, "", long_options, NULL))){
        if(aSet!=0){ // -a 参数必须放在最后, 之后的参数都看作是应用的参数
            break;
        }
        //打印处理的参数
        //printf("start to process %d para\n",optind);
        switch(c){
            case 'h':
                printf ("这里应该打印帮助信息...\n");
                //printf ( HELP_INFO );
                indexArg++;
                break;
            case 'm':
                if(mSet!=0){
                    std::cerr << "WARNING: -m/-mode is set multiple times, the first value is used" << std::endl;
                    indexArg+=2;
                    break;
                }
                mSet++;
                if(strcmp("INTERACTION", optarg)==0){
                    Config.MeasureMode=MEASURE_MODE::INTERACTION;
                }else if(strcmp("APPLICATION", optarg)==0){
                    Config.MeasureMode=MEASURE_MODE::APPLICATION;
                }else if(strcmp("DAEMON", optarg)==0){
                    Config.MeasureMode=MEASURE_MODE::DAEMON;
                }else{
                    std::cout << "ERROR: Invalid measuing mode (-m " << optarg << ")." << std::endl;
                    err = -1;
                }
                indexArg+=2;
                break;
            case 'a':
            {
                if(aSet!=0 || lSet!=0){
                    std::cerr << "WARNING: -a/-app/-l/-applistfile is set multiple times, the first value is used" << std::endl;
                    break;
                }
                aSet++;
                if(argc-indexArg-1 <= 0){ // 缺少应用参数
                    std::cerr << "ERROR: flag -a/-app need application path" << std::endl;
                    err |= 1;
                    return err;
                }

                Config.MeasureMode=MEASURE_MODE::APPLICATION;

                Config.vecAppPath.emplace(Config.vecAppPath.begin(), (char*)NULL);
                Config.vecAppPath[0] = (char*)malloc( sizeof(char) * (strlen(optarg)+1) );
                strcpy(Config.vecAppPath[0], optarg);
                
                Config.vecAppAgrv.emplace(Config.vecAppAgrv.begin(), (char**)NULL);
                Config.vecAppAgrv[0] = (char**)malloc( sizeof(char*) * (argc-indexArg) );
                Config.vecAppAgrv[0][argc-indexArg-1] = NULL;

                // 这里要处理 Config.vecAppAgrv[0][0], 复制可执行文件/命令, 而不要前边的路径
                std::string TmpString = optarg;
                size_t found = TmpString.find_last_of('/');
                TmpString = TmpString.substr(found+1);
                Config.vecAppAgrv[0][0] = (char*)malloc( sizeof(char) * (TmpString.length()+1) );
                strcpy(Config.vecAppAgrv[0][0], TmpString.c_str());
                
                for (int i = indexArg+2; i < argc; i++) {
                    Config.vecAppAgrv[0][i-indexArg-1] = (char*)malloc( sizeof(char) * (strlen(argv[i])+1) );
                    strcpy(Config.vecAppAgrv[0][i-indexArg-1], argv[i]);
                }
            }
                break;
            
            case 'l':
                if(aSet!=0 || lSet!=0){
                    std::cerr << "WARNING: -a/-app/-l/-applistfile is set multiple times, the first value is used" << std::endl;
                    indexArg+=2;
                    break;
                }
                lSet++;
                if(argc-indexArg-1 <= 0){ // 缺少应用参数
                    std::cerr << "ERROR: flag \"-a\" need application path" << std::endl;
                    err |= 1;
                    return err;
                }
                Config.MeasureMode=MEASURE_MODE::APPLICATION;
                err = Config.LoadAppList(optarg);
                indexArg+=2;
                break;
            case 'p':
                if(pSet!=0){
                    std::cerr << "WARNING: -p/-postinterval is set multiple times, the first value is used" << std::endl;
                    indexArg+=2;
                    break;
                }
                pSet++;
                Config.PostInterval = atof(optarg);
                indexArg+=2;
                break;
            case 'o':
                if(oSet!=0){
                    std::cerr << "WARNING: -o/-outfile is set multiple times, the first value is used" << std::endl;
                    indexArg+=2;
                    break;
                }
                oSet++;
                Config.isGenOutFile = true;
                Config.OutFilePath = optarg;
                indexArg+=2;
                break;
            case 'i':
                if(iSet!=0){
                    std::cerr << "WARNING: -i/-id is set multiple times, the first value is used" << std::endl;
                    indexArg+=2;
                    break;
                }
                iSet++;
                Config.DeviceID = atoi(optarg);
                // PM.DeviceIDCUDADrv = Config.DeviceID;
                PM.DeviceIDNVML = Config.DeviceID;

                if(Config.DeviceID < 0){
                    std::cerr << "ERROR: -i/-id value illegal: " << optarg << std::endl;
                    err |= 1;
                }

                indexArg+=2;
                break;
            case 's':
                if(sSet!=0){
                    std::cerr << "WARNING: -s/-samplinginterval is set multiple times, the first value is used" << std::endl;
                    indexArg+=2;
                    break;
                }
                sSet++;
                Config.SampleInterval = atof(optarg);
                indexArg+=2;
                break;
            case 't':
                if(tSet!=0){
                    std::cerr << "WARNING: -t/-threshold is set multiple times, the first value is used" << std::endl;
                    indexArg+=2;
                    break;
                }
                tSet++;
                Config.PowerThreshold = atof(optarg);
                indexArg+=2;
                break;
            case 'e':
                if(eSet!=0){
                    std::cerr << "WARNING: -e/-energy is set multiple times" << std::endl;
                    indexArg++;
                    break;
                }
                eSet++;
                Config.isMeasureEnergy = true;
                indexArg++;
                break;
            case 1:
                if(memutiSet!=0){
                    std::cerr << "WARNING: -memuti is set multiple times" << std::endl;
                    indexArg++;
                    break;
                }
                memutiSet++;
                Config.isMeasureMemUtil = true;
                indexArg++;
                break;
            case 2:
                if(memclkSet!=0){
                    std::cerr << "WARNING: -memclk is set multiple times" << std::endl;
                    indexArg++;
                    break;
                }
                memclkSet++;
                Config.isMeasureMemClk = true;
                indexArg++;
                break;
            case 3:
                if(gpuutiSet!=0){
                    std::cerr << "WARNING: -gpuuti is set multiple times" << std::endl;
                    indexArg++;
                    break;
                }
                gpuutiSet++;
                Config.isMeasureGPUUtil = true;
                indexArg++;
                break;
            case 4:
                if(smclkSet!=0){
                    std::cerr << "WARNING: -smclk is set multiple times" << std::endl;
                    indexArg++;
                    break;
                }
                smclkSet++;
                Config.isMeasureSMClk = true;
                indexArg++;
                break;

            case 0:
                if(tuneSet!=0){
                    std::cerr << "WARNING: -tune is set multiple times, the first value is used" << std::endl;
                    indexArg+=2;
                    break;
                }
                tuneSet++;
                if(strcmp("DVFS", optarg)==0){
                    PM.TuneType = 0;
                }else if(strcmp("POWER", optarg)==0){
                    PM.TuneType = 1;
                }else if(strcmp("SM_RANGE", optarg)==0){
                    PM.TuneType = 2;
                }else{
                    std::cerr << "Power Manager ERROR: Invalid tuning technology type (-tune " << optarg << ")." << std::endl;
                    err |= 1;
                }
                indexArg+=2;
                break;
            case 5:
                if(tuneargSet!=0){
                    std::cerr << "WARNING: -tunearg is set multiple times, the first value is used" << std::endl;
                    indexArg+=2;
                    break;
                }
                tuneargSet++;
                PM.TuneArg = atoi(optarg);
                if(PM.TuneArg < 0){
                    std::cerr << "ERROR: -tunearg value illegal: " << optarg << std::endl;
                    err |= 1;
                }
                indexArg+=2;
                break;
            case 6:
                if(lowerSet!=0){
                    std::cerr << "WARNING: -lower is set multiple times, the first value is used" << std::endl;
                    indexArg+=2;
                    break;
                }
                lowerSet++;
                PM.LowerPct = atof(optarg);
                if(0.0 > PM.LowerPct || PM.LowerPct > 100.0){
                    std::cerr << "ERROR: -lower value illegal: " << optarg << std::endl;
                    err |= 1;
                }
                indexArg+=2;
                break;
            case 7:
                if(upperSet!=0){
                    std::cerr << "WARNING: -upper is set multiple times, the first value is used" << std::endl;
                    indexArg+=2;
                    break;
                }
                upperSet++;
                PM.UpperPct = atof(optarg);
                if(0.0 > PM.UpperPct || PM.UpperPct > 100.0){
                    std::cerr << "ERROR: -upper value illegal: " << optarg << std::endl;
                    err |= 1;
                }
                indexArg+=2;
                break;
            
            case 8:
                if(traceSet!=0){
                    std::cerr << "WARNING: -trace is set multiple times" << std::endl;
                    indexArg+=1;
                    break;
                }
                traceSet++;
                Config.isTrace = true;
                indexArg+=1;
                break;

            //表示选项不支持
            case '?':
                printf("unknow option: %d\n", optopt);
                err |= 1;
                indexArg++;
                break;
            default:
                break;
        }  
    }

    if (tuneargSet > 0 || lowerSet > 0 || upperSet > 0)
    {
        isTuneAtBegin = true;
    }

    err |= PM.initArg(&MyNVML);

    return err;
}