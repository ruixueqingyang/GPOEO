/*******************************************************************************
Copyright(C), 2020-2020, 瑞雪轻飏
     FileName: MsgEPRT.cpp
       Author: 瑞雪轻飏
      Version: 0.01
Creation Date: 20200704
  Description: 向运行时发送信息
       Others: 
*******************************************************************************/

#include "Msg2EPRT.h"

int SendUDPMessage(std::string Msg);

int SetSMClkRange(float LowerPercent, float UpperPercent){
    std::string Msg = "SM_RANGE: ";
    Msg = Msg + std::to_string(LowerPercent) + ", " + std::to_string(UpperPercent);
    return SendUDPMessage(Msg);
}

int ResetSMClk(){
    std::string Msg = "RESET_SM_CLOCK";
    return SendUDPMessage(Msg);
}

int TimeStamp(std::string& Description){
    std::string Msg = "TIME_STAMP: ";
    Msg = Msg + Description;
    return SendUDPMessage(Msg);
}

int StartMeasurement(){
    return SendUDPMessage("START");
}

int StopMeasurement(){
    return SendUDPMessage("STOP");
}

int ExitMeasurement(){
    return SendUDPMessage("EXIT");
}

int ResetMeasurement(){
    return SendUDPMessage("RESET");
}

int ResetMeasurement(std::string& OutPath){
    std::string Msg = "RESET: ";
    Msg += OutPath;
    return SendUDPMessage(Msg);
}

int SendUDPMessage(std::string Msg){
    int client_fd;
    struct sockaddr_in ser_addr;

    client_fd = socket(AF_INET, SOCK_DGRAM, 0);
    if(client_fd < 0){
        std::cout << "WARNING: create socket fail!\n" << std::endl;
        return -1;
    }

    memset(&ser_addr, 0, sizeof(ser_addr));
    ser_addr.sin_family = AF_INET;
    //ser_addr.sin_addr.s_addr = inet_addr(SERVER_IP);
    ser_addr.sin_addr.s_addr = htonl(INADDR_ANY);  //注意网络序转换
    ser_addr.sin_port = htons(SERVER_PORT);  //注意网络序转换

    socklen_t SizeofSockAddr = sizeof(ser_addr);
    // sendto(client_fd, Msg.c_str(), BUFF_LEN, 0, (struct sockaddr*)&ser_addr, SizeofSockAddr);
    sendto(client_fd, Msg.c_str(), Msg.size()+1, 0, (struct sockaddr*)&ser_addr, SizeofSockAddr);

    close(client_fd);

    return 0;
}