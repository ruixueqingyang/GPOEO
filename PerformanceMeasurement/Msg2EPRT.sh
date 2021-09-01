#!/bin/bash

# funWithParam(){
#     echo "第一个参数为 $1 !"
#     echo "第二个参数为 $2 !"
#     echo "第十个参数为 $10 !"
#     echo "第十个参数为 ${10} !"
#     echo "第十一个参数为 ${11} !"
#     echo "参数总数有 $# 个!"
#     echo "作为一个字符串输出所有参数 $* !"
# }

LOCAL_HOST="127.0.0.1"
SERVER_PORT="7777"
# FILE_DESCRIPTOR="3"

function SendUDPMessage(){
    exec 3>/dev/udp/${LOCAL_HOST}/${SERVER_PORT}
    # echo "SendUDPMessage="${1}
    echo ${1} >&3
    exec 3>&-
}

function SetSMClkRange(){
    Msg="SM_RANGE: "${1}", "${2}
    # echo "Msg="${Msg}
    SendUDPMessage "${Msg}"
}

function ResetSMClk(){
    Msg="RESET_SM_CLOCK"
    # echo "Msg="${Msg}
    SendUDPMessage "${Msg}"
}

function TimeStamp(){
    Msg="TIME_STAMP: "${1}
    # echo "Msg="${Msg}
    SendUDPMessage "${Msg}"
}

function StartMeasurement(){
    SendUDPMessage "START"
}

function StopMeasurement(){
    SendUDPMessage "STOP"
}

function ExitMeasurement(){
    SendUDPMessage "EXIT"
}

function ResetMeasurement(){
    Msg="RESET: "${1}
    # echo "Msg="${Msg}
    SendUDPMessage "${Msg}"
}