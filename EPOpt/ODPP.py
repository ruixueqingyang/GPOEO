# -*- coding: utf-8 -*-
# wfr 20210907 实现 ODPP (Indicator-Directed Dynamic Power Management for Iterative Workloads on GPU-Accelerated Systems)
import numpy as np                # 导入模块 numpy，并简写成 np
import matplotlib.pyplot as plt   # 导入模块 matplotlib.pyplot，并简写成 plt 
import pandas as pd
import os
import threading
# import seaborn as sns
import pickle
import time
import multiprocessing
# import torch.multiprocessing as multiprocessing
from multiprocessing import Process, Lock, Manager, Value
import sys
from collections import deque
from itertools import chain
import threading


# lsc writes here~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
isMeasureOverhead = True # set False if want to measure overhead


import sys
import os
tmpDir = os.path.abspath(__file__)
tmpDir = os.path.split(tmpDir)[0]
print("tmpDir = {}".format(tmpDir))
tmpDir = os.path.abspath(tmpDir)
print("tmpDir = {}".format(tmpDir))
sys.path.append(tmpDir)
sys.stdout.flush

import EPOptDrv
from Msg2EPRT import TimeStamp
from StateReward import SetMetric, SelectOptGear, IsBetter, GetReward, GetArrayReward
from SpectrumAnalysis import T_FFT

ProcessODPP = Process()
QueueGlobal = multiprocessing.Queue()
# QueueGlobalWatch = multiprocessing.Queue()

RUN_MODE = {'WORK': int(0), 'LEARN': int(1), 'LEARN_WORK': int(2), 'MEASURE': int(3), 'ODPP': int(4)}

isRun = False
FileCount = 0

def GetTrace(PowerLimit):
    listPowerTrace = EPOptDrv.GetPowerTrace()
    listSMUtilTrace = EPOptDrv.GetSMUtilTrace()
    listMemUtilTrace = EPOptDrv.GetMemUtilTrace()

    arrayPowerTrace = np.array(listPowerTrace)
    arraySMUtilTrace = np.array(listSMUtilTrace)
    arrayMemUtilTrace = np.array(listMemUtilTrace)

    arrayCompositeTrace = (arrayPowerTrace / PowerLimit * 100 + arraySMUtilTrace + arrayMemUtilTrace)/3

    return arrayCompositeTrace, arrayPowerTrace, arraySMUtilTrace, arrayMemUtilTrace

# wfr 20201222 测量直到认为是稳定状态
def MeasureUntilStable(BaseGear, MeasureDurationInit, TUpBound, SampleInterval, PowerThreshold, PowerLimit, TestPrefix):
    global QueueGlobal, isRun, FileCount

    print("MeasureUntilStable: Begin")

    if BaseGear >= 0:
        EPOptDrv.SetEnergyGear(BaseGear)
        print("MeasureUntilStable: Set CurrentGear = {:d}".format(BaseGear))
    time.sleep(1) # 延时 1s, 使频率生效且稳定

    # wfr 20201228 表示是否一定不稳定, 如果总测量时间远大于测出的周期, 且近几次的周期相差较大, 则认为一定是不稳定的, 此时测量仍然继续, 最后测得的周期作为 近似的固定周期, 即之后使用固定周期
    MeasureMaxFactor = 3
    MeasureTFactor = 3
    SumMeasureDuration = 0
    PrevTimeStamp = 0
    MeasureCount = 0
    MeasureDurationNext = MeasureDurationInit
    TEstimated = 1.0

    arrayPowerTrace = np.array([1])
    arraySMUtilTrace = np.array([1])
    arrayMemUtilTrace = np.array([1])

    # 启动测量
    EPOptDrv.StartMeasure([], "SIMPLE_FEATURE_TRACE")
    PrevTimeStamp = time.time() # 记录时间戳
    
    sys.stdout.flush()

    listTEstimated = []
    listMeasureDurationNext = []
    # 循环如果: 还不稳定 且 总测量时间没超过上限 且 总测量时间没超过估计周期的5倍
    while MeasureDurationNext > 0 and SumMeasureDuration < MeasureMaxFactor * TUpBound:

        # print("MeasureUntilStable: MeasureDurationNext = {0} s".format(MeasureDurationNext))
        # print("MeasureUntilStable: SumMeasureDuration = {0} s".format(SumMeasureDuration))

        # 延时, 这里要减去中间数据处理的时间, 因为测量与数据处理并行, 有时间上的重叠
        try:
            tmpDelay = MeasureDurationNext-(time.time()-PrevTimeStamp)
            print("MeasureUntilStable: 延时 {0:.2f} s".format(tmpDelay))
            isRun = QueueGlobal.get( timeout=(tmpDelay) ) # 延时，如果收到进程结束信号则立即结束延时
        except:
            pass
        if isRun == False:
            EPOptDrv.StopMeasure()
            print("MeasureUntilStable: isRun = {}".format(isRun))
            return TEstimated, arrayPowerTrace, arraySMUtilTrace, arrayMemUtilTrace
        
        print("MeasureUntilStable: 延时 complete")
        sys.stdout.flush()

        # 获得 trace
        EPOptDrv.ReceiveData() # 收数据
        PrevTimeStamp = time.time() # 记录时间戳

        arrayCompositeTrace, arrayPowerTrace, arraySMUtilTrace, arrayMemUtilTrace = GetTrace(PowerLimit)

        SumMeasureDuration = len(arrayCompositeTrace) * SampleInterval / 1000
        print("MeasureUntilStable: len of arrayCompositeTrace = {}".format(len(arrayCompositeTrace)))

        # 频谱分析判断是否稳定
        if len(arrayCompositeTrace) == 0:
            print("MeasureUntilStable WARNING: len of arrayCompositeTrace = 0")
            return TEstimated, arrayPowerTrace, arraySMUtilTrace, arrayMemUtilTrace
        else:
            TraceFileName = TestPrefix+"-PowerTarce-"+str(FileCount)
            TEstimated, MeasureDurationNext = T_FFT(arrayCompositeTrace, SampleInterval, TUpBound, MeasureTFactor, TraceFileName)
    
    EPOptDrv.StopMeasure()
    print("MeasureUntilStable: TEstimated = {}".format(TEstimated))
    print("MeasureUntilStable: EPOptDrv.StopMeasure() has returned")
    FileCount += 1
    sys.stdout.flush()
    return TEstimated, arrayPowerTrace, arraySMUtilTrace, arrayMemUtilTrace


def MeasureFeature(BaseGear, MeasureDurationInit, TUpBound, SampleInterval, PowerThreshold, PowerLimit, TestPrefix):
    global QueueGlobal, isRun

    print("\nMeasureFeature: Begin")

    dictFeature = {"Energy": 1e5, "Time": TUpBound, "Power": 1e5 / TUpBound, "SMUtil": 100, "MemUtil": 100}

    if BaseGear >= 0:
        EPOptDrv.SetEnergyGear(BaseGear)
        print("MeasureFeature: Set CurrentGear = {:d}".format(BaseGear))

    TEstimated, arrayPowerTrace, arraySMUtilTrace, arrayMemUtilTrace = MeasureUntilStable(BaseGear, MeasureDurationInit, TUpBound, SampleInterval, PowerThreshold, PowerLimit, TestPrefix)

    dictFeature["Time"] = TEstimated

    if isRun == False:
        print("MeasureFeature: isRun = {}".format(isRun))
        return dictFeature, TEstimated
    sys.stdout.flush()


    # 从 arrayPowerTrace 中取出最后一个 TEstimated 的数据计算特征
    dictFeature["Time"] = TEstimated
    tmpLenEnd = len(arrayPowerTrace)
    tmpLenT = int( round( TEstimated / (SampleInterval/1000) ) ) # 取出最后的 1个 TEstimated 时间内的 采样数据
    tmpLenT = min(tmpLenT, (tmpLenEnd-2))

    array0 = np.array(arrayPowerTrace[(tmpLenEnd-tmpLenT-1):tmpLenEnd])
    array1 = np.array(arrayPowerTrace[(tmpLenEnd-tmpLenT-2):tmpLenEnd-1])
    dictFeature["Power"] = np.mean(array0 + array1)/2 - PowerThreshold # 平均功率 (用一阶线性插值减小误差)
    dictFeature["Energy"] = dictFeature["Power"] * dictFeature["Time"] # 平均功率 * 时间

    array0 = np.array(arraySMUtilTrace[(tmpLenEnd-tmpLenT-1):tmpLenEnd])
    array1 = np.array(arraySMUtilTrace[(tmpLenEnd-tmpLenT-2):tmpLenEnd-1])
    dictFeature["SMUtil"] = np.mean(array0 + array1)/2

    array0 = np.array(arrayMemUtilTrace[(tmpLenEnd-tmpLenT-1):tmpLenEnd])
    array1 = np.array(arrayMemUtilTrace[(tmpLenEnd-tmpLenT-2):tmpLenEnd-1])
    dictFeature["MemUtil"] = np.mean(array0 + array1)/2

    # 检查是否停止运行
    try:
        isRun = QueueGlobal.get(block = False)
    except:
        pass
    if isRun == False:
        print("MeasureFeature: isRun = {}".format(isRun))
        return dictFeature

    return dictFeature


# wfr 20201222 测量直到认为是不稳定状态
def MeasureUntilUnstable(MeasureDurationInit, TUpBound, SampleInterval, PowerThreshold, PowerLimit, TestPrefix):
    global QueueGlobal, isRun

    PowerError = 0.15

    SimpleCount = 0
    dequePower = deque([])
    dequeSMUtil = deque([])
    dequeMemUtil = deque([])

    TEstimated, arrayPowerTrace, arraySMUtilTrace, arrayMemUtilTrace = MeasureUntilStable(int(-1), MeasureDurationInit, TUpBound, SampleInterval, PowerThreshold, PowerLimit, TestPrefix)

    if isRun == False:
        print("MeasureUntilUnstable: isRun = {}".format(isRun))
        return

    tmpLenEnd = len(arrayPowerTrace)
    tmpMeasureDuration = (tmpLenEnd - 1) * (SampleInterval / 1000)
    tmpMeasureCount = int(np.floor( tmpMeasureDuration / TEstimated ))
    tmpLenT = int( round( TEstimated / (SampleInterval/1000) ) ) # 取出最后的 TEstimated 时间内的 采样数据
    for i in range(tmpMeasureCount-1):
        tmpIndexBegin = tmpLenEnd - (i+1) * tmpLenT - 1
        tmpIndexEnd = tmpLenEnd - (i) * tmpLenT

        array0 = np.array(arrayPowerTrace[tmpIndexBegin:tmpIndexEnd])
        tmpPower = np.mean(array0) - PowerThreshold # 平均功率
        if len(dequePower) != 2:
            dequePower.append(tmpPower) # init min power
            dequePower.append(tmpPower) # init max power
        else:
            if tmpPower < dequePower[0]:
                dequePower[0] = tmpPower
            elif tmpPower > dequePower[1]:
                dequePower[1] = tmpPower

        array0 = np.array(arraySMUtilTrace[tmpIndexBegin:tmpIndexEnd])
        tmpSMUtil = np.mean(array0) # 平均功率
        if len(dequeSMUtil) != 2:
            dequeSMUtil.append(tmpSMUtil) # init min SMUtil
            dequeSMUtil.append(tmpSMUtil) # init max SMUtil
        else:
            if tmpSMUtil < dequeSMUtil[0]:
                dequeSMUtil[0] = tmpSMUtil
            elif tmpSMUtil > dequeSMUtil[1]:
                dequeSMUtil[1] = tmpSMUtil

        array0 = np.array(arrayMemUtilTrace[tmpIndexBegin:tmpIndexEnd])
        tmpMemUtil = np.mean(array0) # 平均功率
        if len(dequeMemUtil) != 2:
            dequeMemUtil.append(tmpMemUtil) # init min MemUtil
            dequeMemUtil.append(tmpMemUtil) # init max MemUtil
        else:
            if tmpMemUtil < dequeMemUtil[0]:
                dequeMemUtil[0] = tmpMemUtil
            elif tmpMemUtil > dequeMemUtil[1]:
                dequeMemUtil[1] = tmpMemUtil

        print("tmpPower = {}".format(tmpPower))
        print("tmpSMUtil = {}".format(tmpSMUtil))
        print("tmpMemUtil = {}".format(tmpMemUtil))
        sys.stdout.flush()

    SimpleCount += tmpMeasureCount-1


    sys.stdout.flush()
    while True:
        EPOptDrv.StartMeasure([], "SIMPLE_FEATURE_TRACE")
        tmpTimeStampStart = time.time()

        try:
            tmpDelay = TEstimated
            print("MeasureUntilUnstable: 延时 {0:.2f} s".format(tmpDelay))
            isRun = QueueGlobal.get( timeout=(tmpDelay+1.5) ) # 延时，如果收到进程结束信号则立即结束延时
        except:
            pass
        if isRun == False:
            EPOptDrv.StopMeasure()
            print("MeasureUntilUnstable: isRun = {}".format(isRun))
            return


        EPOptDrv.StopMeasure()
        print("MeasureUntilUnstable: GetTrace")
        arrayCompositeTrace, arrayPowerTrace, arraySMUtilTrace, arrayMemUtilTrace = GetTrace(PowerLimit)
        print("MeasureUntilUnstable: len of arrayPowerTrace = {}".format(len(arrayPowerTrace)))
        sys.stdout.flush()
        
        tmpLenT = int( round( tmpDelay / (SampleInterval/1000) ) ) # 取出最后的 tmpDelay 时间内的采样点
        tmpLenEnd = len(arrayPowerTrace)

        dictFeature = {"Energy": 1e5, "Time": TUpBound, "Power": 1e5 / TUpBound, "SMUtil": 100, "MemUtil": 100}
        if tmpLenEnd >= tmpLenT:
            tmpIndexBegin = tmpLenEnd - tmpLenT - 1
            tmpIndexEnd = tmpLenEnd
            array0 = np.array(arrayPowerTrace[tmpIndexBegin:tmpIndexEnd])
            dictFeature["Power"] = np.mean(array0) - PowerThreshold # 平均功率
            dictFeature["Time"] = TEstimated
            dictFeature["Energy"] = dictFeature["Power"] * dictFeature["Time"]
            array0 = np.array(arraySMUtilTrace[tmpIndexBegin:tmpIndexEnd])
            dictFeature["SMUtil"] = np.mean(array0)
            array0 = np.array(arrayMemUtilTrace[tmpIndexBegin:tmpIndexEnd])
            dictFeature["MemUtil"] = np.mean(array0)

        else:
            dictFeature = EPOptDrv.GetFeature() # 读取数据
            print("MeasureUntilUnstable: dictFeature:")
            print(dictFeature)

        SimpleCount += 1
        sys.stdout.flush()
        
        # 如果是首次 简测量，就 清空队列 再 保存第一次的 dictFeature["Power"] 既为最小值也为最大值
        # dequePower[0] 保存最小值，dequePower[1] 保存最大值
        if len(dequePower) != 2:
            dequePower.clear()
            dequePower.append(dictFeature["Power"])
            dequePower.append(dictFeature["Power"])
        else:
            if dictFeature["Power"] < dequePower[0]:
                dequePower[0] = dictFeature["Power"]
            elif dictFeature["Power"] > dequePower[1]:
                dequePower[1] = dictFeature["Power"]
        minPower = min(dequePower)
        maxPower = max(dequePower)
        meanPower = sum(dequePower) / len(dequePower)

        if len(dequeSMUtil) != 2:
            dequeSMUtil.clear()
            dequeSMUtil.append(dictFeature["SMUtil"])
            dequeSMUtil.append(dictFeature["SMUtil"])
        else:
            if dictFeature["SMUtil"] < dequeSMUtil[0]:
                dequeSMUtil[0] = dictFeature["SMUtil"]
            elif dictFeature["SMUtil"] > dequeSMUtil[1]:
                dequeSMUtil[1] = dictFeature["SMUtil"]
        minSMUtil = min(dequeSMUtil)
        maxSMUtil = max(dequeSMUtil)
        meanSMUtil = sum(dequeSMUtil) / len(dequeSMUtil)

        if len(dequeMemUtil) != 2:
            dequeMemUtil.clear()
            dequeMemUtil.append(dictFeature["MemUtil"])
            dequeMemUtil.append(dictFeature["MemUtil"])
        else:
            if dictFeature["MemUtil"] < dequeMemUtil[0]:
                dequeMemUtil[0] = dictFeature["MemUtil"]
            elif dictFeature["MemUtil"] > dequeMemUtil[1]:
                dequeMemUtil[1] = dictFeature["MemUtil"]
        minMemUtil = min(dequeMemUtil)
        maxMemUtil = max(dequeMemUtil)
        meanMemUtil = sum(dequeMemUtil) / len(dequeMemUtil)

        print("tmpPower = {}".format(dictFeature["Power"]))
        print("tmpSMUtil = {}".format(dictFeature["SMUtil"]))
        print("tmpMemUtil = {}".format(dictFeature["MemUtil"]))
        sys.stdout.flush()

        # 偏差过大则认为应用运行进入不稳定状态
        if abs((maxPower-minPower)/meanPower) > PowerError:
        # if abs((maxPower-minPower)/meanPower) > PowerError \
        #     or abs((maxSMUtil-minSMUtil)/meanSMUtil) > PowerError \
        #     or abs((maxMemUtil-minMemUtil)/meanMemUtil) > PowerError:

            print("MeasureUntilUnstable: dequePower: {}".format(dequePower))
            print("MeasureUntilUnstable: dequeSMUtil: {}".format(dequeSMUtil))
            print("MeasureUntilUnstable: dequeMemUtil: {}".format(dequeMemUtil))
            print("MeasureUntilUnstable: 进入不稳定状态")
            sys.stdout.flush()
            return

        # 多次简测量, 应用都是稳定状态, 则 休眠一段时间
        elif SimpleCount >= 3:
            print("MeasureUntilUnstable: 仍是稳定状态")
            NumInterval = pow(2, SimpleCount-1) # 指数增加 测量间隔
            NumInterval = min(NumInterval, 32) # 间隔数量上限是 32 个测量持续时间
            sys.stdout.flush()
            try:
                tmpDelay = NumInterval * TEstimated
                print("MeasureUntilUnstable: 休眠 {0:.2f} s".format(tmpDelay))
                isRun = QueueGlobal.get( timeout=(tmpDelay) ) # 延时，如果收到进程结束信号则立即结束延时
            except:
                pass
            if isRun == False:
                print("Manager Process: isRun = {}".format(isRun))
                return
        sys.stdout.flush()
    return

def ODPP(inDeviceIDCUDADrv, inDeviceIDNVML, inRunMode="MLP", inMeasureOutDir="NONE", inModelDir="/home/wfr/work/Energy/ODPP", inTestPrefix=""):
    global QueueGlobal, isRun
    print("run: ODPP Process")

    #进程ID
    PID = os.getpid()
    print("ODPP: PID = {:x}".format(PID))
    # 1 获取线程ID,NAME
    tmpThread = threading.currentThread()
    #线程ID
    print("ODPP: TID = {:x}".format(tmpThread.ident))

    os.environ["CUDA_DEVICE_ORDER"]="PCI_BUS_ID"
    os.environ["CUDA_VISIBLE_DEVICES"]="-1"

    try:
        del torch
    except:
        pass
    try:
        del nn
    except:
        pass
    try:
        del F
    except:
        pass
    try:
        del optim
    except:
        pass
    try:
        del DataLoader
    except:
        pass

    # import torch
    # from torch import nn
    from ODPPModel import ODPP_AM_MLP

    # wfr 20210907 运行状态为 False 直接退出
    if isRun == False:
        print("ODPP: isRun = {}".format(isRun))
        return

    # wfr 20210909 初始化相关参数
    NumSamples = 4 # wfr 20210921 AM 初始化采样点数量
    DeviceIDCUDADrv = inDeviceIDCUDADrv
    DeviceIDNVML = inDeviceIDNVML
    RunMode = inRunMode
    MeasureOutDir = inMeasureOutDir
    ModelDir = inModelDir
    TestPrefix = inTestPrefix
    MeasureDurationInit = 25
    isMeasurePower = True
    isMeasurePerformace = True
    MEASURE_STOP_MODE = {"TIMER": int(0), "SIGNAL": int(1)}


    isInit = EPOptDrv.ManagerInit(DeviceIDNVML, RUN_MODE["ODPP"], MEASURE_STOP_MODE["SIGNAL"])
    print("ManagerInit = {:d}".format(isInit))
    if isInit < 0:
        return
    

    listFeatureName = ["Energy", "Time", "Power", "SMUtil", "MemUtil"]
    tmplist = [2.333] * len(listFeatureName)
    dictFeature = dict(zip(listFeatureName, tmplist))
    dictFeatureBase = dictFeature

    SMClkGearCount = int(EPOptDrv.GetSMClkGearCount() ) # 0, 1, 2, ..., SMClkGearCount-1
    NumGears = SMClkGearCount
    BaseSMClk = 1920 # int(EPOptDrv.GetBaseSMClk())
    MinSMClk= int(EPOptDrv.GetMinSMClk())
    print("MinSMClk = {}".format(MinSMClk))
    SMClkStep = int(EPOptDrv.GetSMClkStep())
    print("SMClkStep = {}".format(SMClkStep))
    GPUName = EPOptDrv.GetGPUName()
    GPUName = GPUName.replace("NVIDIA","").replace("GeForce","").replace(" ","")
    print("GPUName: {}".format(GPUName))
    if GPUName == "RTX3080Ti":
        PowerThreshold = 32.0
    elif GPUName == "RTX2080Ti":
        PowerThreshold = 1.65
    else:
        PowerThreshold = 0.0
    BaseGear = int((BaseSMClk - MinSMClk) / SMClkStep)
    PowerLimit = EPOptDrv.GetPowerLimit()
    
    TUpBound = 60
    SampleInterval = 100 # 采样周期 单位是 ms

    print("MinSMClk = {:d}; BaseSMClk = {:d}; SMClkStep = {:d}".format(MinSMClk, BaseSMClk, SMClkStep))
    print("SMClkGearCount = {:d}; BaseGear = {:d}".format(SMClkGearCount, BaseGear))
    sys.stdout.flush

    SMUtil = int(100)
    SMUnusedRatioThreshold = 0.1
    PredictedOptGear = int(-1)
    SimpleCount = 0
    dequePower = deque([]) # 初始化功率队列
    Obj = "Energy" # "ED2P" "EDP" "Energy" "Performance"
    PerfLoss = 0.045 # require performace loss within 4.5%
    EngSave = 0.10 # require energy saving over 10%
    Threshold = PerfLoss

    if SMClkGearCount <= 0:
        print("EPOpt ERROR: 获得 SMClkGearCount 错误")
        os._exit(0)


    isInit = EPOptDrv.MeasurerInit(DeviceIDCUDADrv, DeviceIDNVML, RunMode, MEASURE_STOP_MODE["SIGNAL"], [], MeasureDurationInit, isMeasurePower, isMeasurePerformace)
    if isInit < 0:
        return
    while isRun == True:

        # wfr 20210921 初始化模型, 加载 MLP 模型
        EngModel = ODPP_AM_MLP()
        TimeModel = ODPP_AM_MLP()
        try:
            EngMLPDir = os.path.join(ModelDir, "Eng", "ODPP_EngMLP-"+str(NumSamples))
            TimeMLPDir = os.path.join(ModelDir, "Time", "ODPP_TimeMLP-"+str(NumSamples))
            EngModel.MLP.load_weights(EngMLPDir)
            TimeModel.MLP.load_weights(TimeMLPDir)
            print("ODPP: 初始化 AM_MLP 模型完成")
            TimeStamp("ODPP Init Complete")
        except:
            print("ODPP ERROR: 初始化 AM_MLP 模型")
            break

        # wfr 20210921 采样, 建立 AM 模型
        ClockLowerBound = 450
        ClockUpperBound = BaseSMClk
        arraySampleClock = np.arange(ClockLowerBound, ClockUpperBound, (ClockUpperBound-ClockLowerBound)/(NumSamples-1)+1e-3)
        arraySampleClock = np.append(arraySampleClock, ClockUpperBound)
        arraySampleClock = np.round((arraySampleClock - ClockLowerBound) / SMClkStep) * SMClkStep + ClockLowerBound
        arraySampleClock = arraySampleClock.astype(int)
        print("arraySampleClock = {}".format(arraySampleClock))

        arraySampleEng = np.zeros(len(arraySampleClock))
        arraySampleTime = np.zeros(len(arraySampleClock))

        for i in range(len(arraySampleClock)):
            SampleClock = arraySampleClock[i]
            SampleGear = int((SampleClock - MinSMClk) / SMClkStep)
            dictFeature = MeasureFeature(SampleGear, MeasureDurationInit, TUpBound, SampleInterval, PowerThreshold, PowerLimit, TestPrefix)
            # 检查是否停止运行
            try:
                isRun = QueueGlobal.get(block = False)
            except:
                pass
            if isRun == False or len(dictFeature) == 0:
                break
            arraySampleEng[i] = dictFeature["Energy"]
            arraySampleTime[i] = dictFeature["Time"]
            if i == len(arraySampleClock) - 1:
                dictFeatureBase = dictFeature
        if len(dictFeature) == 0:
            break
        
        print("arraySampleEng = {}".format(arraySampleEng))
        print("arraySampleTime = {}".format(arraySampleTime))
        EngModel.AM.Init(arraySampleClock, arraySampleClock, arraySampleEng)
        TimeModel.AM.Init(arraySampleClock, arraySampleClock, arraySampleTime)
        print("ODPP: 建立 AM 模型完成")
        TimeStamp("ODPP AM Complete")

        # wfr 20210921 采样, 重新训练 MLP 模型
        arrayCalibrateClock = (arraySampleClock[:-1] + arraySampleClock[1:]) / 2
        arrayCalibrateClock = np.round((arrayCalibrateClock - ClockLowerBound) / SMClkStep) * SMClkStep + ClockLowerBound
        arrayCalibrateClock = arrayCalibrateClock.astype(int)
        print("arrayCalibrateClock = {}".format(arrayCalibrateClock))

        arrayCalibrateEng = np.zeros(len(arrayCalibrateClock))
        arrayCalibrateTime = np.zeros(len(arrayCalibrateClock))

        for i in range(len(arrayCalibrateClock)):
            CalibrateClock = arrayCalibrateClock[i]
            CalibrateGear = int((CalibrateClock - MinSMClk) / SMClkStep)
            dictFeature = MeasureFeature(CalibrateGear, MeasureDurationInit, TUpBound, SampleInterval, PowerThreshold, PowerLimit, TestPrefix)
            # 检查是否停止运行
            try:
                isRun = QueueGlobal.get(block = False)
            except:
                pass
            if isRun == False or len(dictFeature) == 0:
                break
            arrayCalibrateEng[i] = dictFeature["Energy"]
            arrayCalibrateTime[i] = dictFeature["Time"]
        if len(dictFeature) == 0:
            break

        print("arrayCalibrateEng = {}".format(arrayCalibrateEng))
        print("arrayCalibrateTime = {}".format(arrayCalibrateTime))
        arrayFeature = np.array([dictFeatureBase["Power"], dictFeatureBase["SMUtil"], dictFeatureBase["MemUtil"]]).reshape(1, -1)
        arrayClockRelative = (arrayCalibrateClock / BaseSMClk).reshape(-1, 1)
        arrayFeature = np.repeat(arrayFeature, len(arrayCalibrateClock), axis=0)
        arrayFeature = np.hstack([arrayClockRelative, arrayFeature])
        batch_size = 256
        epochs = 20
        EngModel.RetrainMLP(arrayCalibrateClock, arrayCalibrateClock, arrayCalibrateEng, arrayFeature, batch_size, epochs, "Energy Model")
        TimeModel.RetrainMLP(arrayCalibrateClock, arrayCalibrateClock, arrayCalibrateTime, arrayFeature, batch_size, epochs, "Energy Model")
        print("ODPP: 重新训练 MLP 模型完成")
        TimeStamp("ODPP Retraining Complete")

        # 检查是否停止运行
        try:
            isRun = QueueGlobal.get(block = False)
        except:
            pass
        if isRun == False:
            break

        # wfr 20210921 wfr 使用在线重新训练后的 AM + MLP 模型预测所有频率的 能耗/性能表现
        arrayClock = np.arange(ClockLowerBound, ClockUpperBound, SMClkStep - 1e-7)
        arrayClock = np.round((arrayClock - ClockLowerBound) / SMClkStep) * SMClkStep + ClockLowerBound
        arrayClock = arrayClock.astype(int)
        arrayGear = ((arrayClock - MinSMClk) / SMClkStep).astype(int)

        arrayFeature = np.array([dictFeature["Power"], dictFeature["SMUtil"], dictFeature["MemUtil"]]).reshape(1, -1)
        arrayClockRelative = (arrayClock / BaseSMClk).reshape(-1, 1)
        arrayFeature = np.repeat(arrayFeature, len(arrayClock), axis=0)
        arrayFeature = np.hstack([arrayClockRelative, arrayFeature])

        arrayEngPrediction = EngModel.Predict(arrayClock, arrayFeature)
        arrayTimePrediction = TimeModel.Predict(arrayClock, arrayFeature)

        # 检查是否停止运行
        try:
            isRun = QueueGlobal.get(block = False)
        except:
            pass
        if isRun == False:
            break
        
        # 选择最优频率
        ConstraintDefault = 1.0
        PredictedReward, PredictedConstraint = GetArrayReward(arrayEngPrediction, arrayTimePrediction, Obj, ConstraintDefault)
        

        PredictedOptGear = SelectOptGear(arrayGear, PredictedReward, PredictedConstraint, Obj, Threshold)
        print("Optimization Object: {}".format(Obj))
        print("ODPP: Predicted Opt Gear = {}".format(PredictedOptGear))

        # 设置最优频率
        EPOptDrv.SetEnergyGear(PredictedOptGear)
        print("ODPP: Set CurrentGear = {:d}".format(PredictedOptGear))
        sys.stdout.flush

        TimeStamp("Begin MeasureUntilUnstable")
        print("Begin MeasureUntilUnstable")
        MeasureUntilUnstable(MeasureDurationInit, TUpBound, SampleInterval, PowerThreshold, PowerLimit, TestPrefix)

        # 检查是否停止运行
        try:
            isRun = QueueGlobal.get(block = False) # 延时，如果收到进程结束信号则立即结束延时
        except:
            pass
    # end while
    
    print("ODPP: isRun = {}".format(isRun))
    EPOptDrv.ManagerStop()
    EPOptDrv.MeasurerSendStopSignal2Manager()
    EPOptDrv.MeasurerStop()
    print("ODPP: End")
    sys.stdout.flush()

def ODPPBegin(inDeviceIDCUDADrv, inDeviceIDNVML, inRunMode="ODPP", inMeasureOutDir="NONE", inModelDir="/home/wfr/work/Energy/ODPP", inTestPrefix=""):
    global isRun
    # wfr 20210907 初始化
    if isRun == True:
        return # 防止重复启动
    else:
        isRun = True

    #进程ID
    PID = os.getpid()
    print("ODPPBegin(): PID = {:x}".format(PID))
    # 1 获取线程ID,NAME
    tmpThread = threading.currentThread()
    #线程ID
    print("ODPPBegin(): TID = {:x}".format(tmpThread.ident))

    RunMode = RUN_MODE[inRunMode]
    print("ODPPBegin(): inRunMode = {}".format(inRunMode))
    print("ODPPBegin(): RunMode = {}".format(RunMode))

    # wfr 20210907 启动 ODPP 进程
    ProcessODPP = Process(target=ODPP, args=(inDeviceIDCUDADrv, inDeviceIDNVML, RunMode, inMeasureOutDir, inModelDir, inTestPrefix))
    ProcessODPP.start()
    

def ODPPEnd():

    if isRun != True:
        return

    # wfr 20210907 结束 ODPP 进程
    try:
        QueueGlobal.put(False, block = False)
        print("QueueGlobal.put(False, block = False)")
        sys.stdout.flush()
    except:
        pass

    try:
        ProcessODPP.terminate()
    except:
        pass
    try:
        ProcessODPP.join()
    except:
        pass

