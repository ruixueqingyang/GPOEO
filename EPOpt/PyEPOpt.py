# -*- coding: utf-8 -*-
import math
import numpy as np
import os
import threading
import pickle
import time
import datetime
import multiprocessing
from multiprocessing import Process, Lock, Manager, Value
import sys
from collections import deque
from itertools import chain



# lsc writes here~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
isMeasureOverhead = False # set True if want to measure overhead


import sys
import os
tmpDir = os.path.abspath(__file__)
tmpDir = os.path.split(tmpDir)[0]
# print("tmpDir = {}".format(tmpDir))
tmpDir = os.path.abspath(tmpDir)
# print("tmpDir = {}".format(tmpDir))
sys.path.append(tmpDir)

import EPOptDrv
from Msg2EPRT import TimeStamp
from StateReward import SetMetric, SelectOptGear, IsBetter, GetReward, GetArrayReward, GetArrayRewardIPS
from SpectrumAnalysis import T_SpectrumAnalysis

QueueGlobal = multiprocessing.Queue()
QueueGlobalWatch = multiprocessing.Queue()

# wfr 20210826 start a thread for this func to handle SMUtil == 0
def WatchSMUsed0(SMUtilTolerateFlag, SMUtil0_TolerateDuration, SMUsedDuraiton, SMUnusedDuraiton, SearchedOptGear, PredictedOptGear, CurrentGear, SearchedOptMemClk, PredictedOptMemClk, CurrentMemClk):
    global QueueGlobalWatch

    print("WatchSMUsed0: Process: Begin")
    sys.stdout.flush()

    tmpBeginTime = time.time()
    tmpUnusedBegin = -1.0
    tmpUsedBegin = -1.0
    # wfr 20210829 init
    if SMUtilTolerateFlag.value == True:
        tmpUsedBegin = time.time()
    else:
        tmpUnusedBegin = time.time()

    isRun = True
    EPOptDrv.NVMLInit()

    try:
        isRun = QueueGlobalWatch.get(block = False)
    except:
        pass
    if isRun == False:
        print("WatchSMUsed0: Process: isRun = {}, in sleep".format(isRun))
        return

    while isRun == True:
        SMUtil = EPOptDrv.GetCurrGPUUtil()
        # print("WatchSMUsed0: SMUtil = {} %; Time = {:.2f} s".format(SMUtil, time.time()-tmpBeginTime))

        if SMUtilTolerateFlag.value == True: # wfr 20210829 SM is used
            if SMUtil == 0: # SMUtil == 0 last SMUtil0_TolerateDuration then SMUtilTolerateFlag = False
                if tmpUnusedBegin < 0:
                    tmpUnusedBegin = time.time()

                elif time.time() - tmpUnusedBegin > SMUtil0_TolerateDuration.value:
                    SMUsedDuraiton.value = time.time() - tmpUsedBegin
                    print("WatchSMUsed0: SMUsedDuraiton = {}".format(SMUsedDuraiton.value))
                    tmpUsedBegin = -1.0

                    SMUtilTolerateFlag.value = False
                    print("WatchSMUsed0: SMUtilTolerateFlag = {}".format(SMUtilTolerateFlag.value))
                    CurrentGear.value = int(0)
                    CurrentMemClk.value = int(405)
                    if isMeasureOverhead == False:
                        EPOptDrv.SetEnergyGear(CurrentGear.value)
                        EPOptDrv.SetMemClkRange(CurrentMemClk.value, CurrentMemClk.value)
                    print("WatchSMUsed0: Set CurrentGear = {:d}".format(CurrentGear.value))
                    print("WatchSMUsed0: Set CurrentMemClk = {:d}".format(CurrentMemClk.value))
            else:
                tmpUnusedBegin = -1.0

        else: # wfr 20210829 SM is unused
            if SMUtil != 0:
                if tmpUsedBegin < 0:
                    tmpUsedBegin = time.time()

                elif time.time() - tmpUsedBegin > SMUtil0_TolerateDuration.value:
                    SMUnusedDuraiton.value = time.time() - tmpUnusedBegin
                    print("WatchSMUsed0: SMUnusedDuraiton = {}".format(SMUnusedDuraiton.value))
                    tmpUnusedBegin = -1.0
                    SMUtilTolerateFlag.value = True
                    print("WatchSMUsed0: SMUtilTolerateFlag = {}".format(SMUtilTolerateFlag.value))

                    if SearchedOptMemClk.value > 0:
                        CurrentMemClk.value = int(SearchedOptMemClk.value)
                        if isMeasureOverhead == False:
                            EPOptDrv.SetMemClkRange(SearchedOptMemClk.value, SearchedOptMemClk.value)
                        print("WatchSMUsed0: Reset CurrentMemClk = {:d}".format(SearchedOptMemClk.value))
                    elif PredictedOptMemClk.value > 0:
                        CurrentMemClk.value = int(PredictedOptMemClk.value)
                        if isMeasureOverhead == False:
                            EPOptDrv.SetMemClkRange(PredictedOptMemClk.value, PredictedOptMemClk.value)
                        print("WatchSMUsed0: Reset CurrentMemClk = {:d}".format(PredictedOptMemClk.value))
                    else:
                        EPOptDrv.ResetMemClkRange()
                        print("WatchSMUsed0: ResetMemClkRange")

                    if SearchedOptGear.value > 0:
                        CurrentGear.value = SearchedOptGear.value
                        if isMeasureOverhead == False:
                            EPOptDrv.SetEnergyGear(CurrentGear.value)
                        print("WatchSMUsed0: Reset CurrentGear = {:d}".format(CurrentGear.value))
                    elif PredictedOptGear.value > 0:
                        CurrentGear.value = PredictedOptGear.value
                        if isMeasureOverhead == False:
                            EPOptDrv.SetEnergyGear(CurrentGear.value)
                        print("WatchSMUsed0: Reset CurrentGear = {:d}".format(CurrentGear.value))
                    else:
                        EPOptDrv.ResetEnergyGear()
                        print("WatchSMUsed0: ResetEnergyGear")

            else:
                tmpUsedBegin = -1.0

        sys.stdout.flush()
        try:
            isRun = QueueGlobalWatch.get( timeout=(1) ) # 延时，如果收到进程结束信号则立即结束延时
        except:
            pass
        if isRun == False:
            print("WatchSMUsed0: Process: isRun = {}, in sleep".format(isRun))
            break

    EPOptDrv.NVMLUninit()

    print("WatchSMUsed0: Process: End")
    sys.stdout.flush()


class EP_OPT(multiprocessing.Process):

    listMetricGroup = []
    listMetricIPS = [] # wfr 20210709 to handle aperiodic APPs
    listFeatureName = []
    dictFeature = {}
    # SMClkGearCount = 103 # 0, 1, 2, ..., SMClkGearCount-1
    SMClkGearCount = int(115)
    # BaseGear = 70 # 1350 MHz(70); 1545 MHz(83)
    BaseGear = int(106) # 1800 MHz(106) 1365 MHz(77)
    MinSMClk = int(210)
    MaxSMClk = int(1830)
    BaseSMClk = int(1800)
    SMClkStep = int(15)
    PowerLimit = 380
    arrayMemClk = np.array([405, 810, 5001, 9251, 9501]).astype(int)
    MemClkBase = int(9501)
    # CurrentGear = int(-1)
    GPUName = "RTX3080Ti"
    # TUpper = 1e9
    # TLower = 0
    TPrev = -1
    TNextPreference = int(0)
    SMClkPrev = int(1000)
    SMUtil = int(100)
    SMUsedBeginTimeStamp = -1.0
    SMUnusedCount = int(0)
    SMUnusedRatioThreshold = 0.1
    TimeIncFactor = 1.1 # 1.05
    TimeDecFactor = 1.0 # 0.98
    IPSIncFactor = 1.0 # 1.02
    EngDecFactor = 1.0 # 0.95
    LocalSearchState = "RESTART" # "RESTART" / "CONTINUE"
    IntMax = int(999999999)

    def __init__(self):
        pid = os.getpid()
        # p = psutil.Process(pid)
        print('Process id : %d' % pid)
        t = threading.currentThread()
        #线程ID
        print('Thread id : %d' % t.ident)
        multiprocessing.Process.__init__(self)

        pid = os.getpid()
        # p = psutil.Process(pid)
        print('Process id : %d' % pid)
        t = threading.currentThread()
        #线程ID
        print('Thread id : %d' % t.ident)

        # self.isMeasureOverHead = False # wfr 20210504 measure cupti overhead

        self.isMeasurePower = True
        self.isMeasurePerformace = True
        self.SampleInterval = 100 # 采样周期 单位是 ms
        self.isRun = False
        # self.lockIsRun = multiprocessing.Lock()
        self.DeviceIDCUDADrv = -1
        self.DeviceIDNVML = -1
        self.RUN_MODE = {'WORK': int(0), 'LEARN': int(1), 'LEARN_WORK': int(2), 'MEASURE': int(3)}
        self.RunMode = 0
        self.MEASURE_STOP_MODE = {"TIMER": int(0), "SIGNAL": int(1)}
        # self.MEASURE_BEGIN_SIGNAL = {"SIMPLE": int(0), "FULL": int(1)}
        self.MeasureMode = 1
        self.MeasureOutDir = "NONE"
        self.ModelDir = ""
        self.TestPrefix = ""

        self.arrayCompositeTrace = np.array([0, 0])
        self.arrayPowerTrace = np.array([0, 0])
        self.arraySMUtilTrace = np.array([0, 0])
        self.arrayMemUtilTrace = np.array([0, 0])
        self.Obj = "Energy" # "ED2P"
        self.PerfLoss = 0.045 # require performace loss within 10%
        self.EngSave = 0.040 # require energy saving over 10%
        self.Threshold = -1.0

        self.NumGears = self.SMClkGearCount

        self.TFixedDefault = 4
        self.TFixed = self.TFixedDefault
        self.TUpBound = 15 # 考虑的最大周期 15
        self.TUpBoundNew = self.TUpBound # 考虑的最大周期
        self.MeasureDurationInit = 25
        
        self.FileCount = 0

        # 初始化开始测量信号，初始化为全测量，即测量性能计数器
        self.SimpleCount = 0
        self.isStateStable = False

        print("Manager Init complete")

    # wfr 20210823 reset T history information
    def ResetTRange(self):
        # self.TUpper = 1e9
        # self.TLower = 0
        self.TPrev = -1
        self.SMClkPrev = int((self.MinSMClk + self.MaxSMClk) / 2)

    #  wfr 20210823 save T history information
    def SaveTPrev(self, TPrev, GearPrev):
        self.TPrev = TPrev
        self.SMClkPrev = int(self.MinSMClk + GearPrev * self.SMClkStep)

    # wfr 20210823 EsimateTRange according to history information
    def EsimateTRange(self, GearCurr):
        if self.TPrev < 0:
            self.TNextPreference = int(0)
        SMClkCurr = int(self.MinSMClk + GearCurr * self.SMClkStep)
        if SMClkCurr > self.SMClkPrev and np.abs(SMClkCurr - self.SMClkPrev) < 1000:
            self.TNextPreference = int(-1)
        elif SMClkCurr < self.SMClkPrev and np.abs(SMClkCurr - self.SMClkPrev) < 1000:
            self.TNextPreference = int(1)
        elif SMClkCurr == self.SMClkPrev:
            self.TNextPreference = int(1)
        else:
            self.TNextPreference = int(0)

        print("EsimateTRange: TPrev = {}; TNextPreference = {}".format(self.TPrev, self.TNextPreference))
        
        return self.TPrev, self.TNextPreference

    def IsSMUnusedPeriodly(self):
        if self.SMUnusedCount>=3 and self.SMUnusedDuraiton.value / self.SMUsedDuraiton.value > self.SMUnusedRatioThreshold:
            return True
        else:
            return False

    # wfr 20210825 is SMUtil == 0 stably or not
    def TestSMUtil(self):
        return self.SMUtilTolerateFlag.value
        
    # wfr 20210824 when SMUtil == 0%, enter this func, until SMUtil > 0%, then return from this func
    def MeasureUntilSMUsed(self):
        global QueueGlobal
        print("MeasureUntilSMUsed: Begin")
        tmpTimeStamp = time.time()

        tmpSMClk = int(EPOptDrv.GetCurrSMClk())
        print("MeasureUntilSMUsed: GetCurrSMClk = {}".format(tmpSMClk))

        if self.SMUtilTolerateFlag.value == False and tmpSMClk != self.MinSMClk:
            self.CurrentGear.value = int(0*self.NumGears)
            if isMeasureOverhead == False:
                EPOptDrv.SetEnergyGear(self.CurrentGear.value)
            print("MeasureUntilSMUsed: Set CurrentGear = {:d}".format(self.CurrentGear.value))
            sys.stdout.flush()

        # self.SMUtil = int(0)
        while self.SMUtilTolerateFlag.value == False:

            try:
                self.isRun = QueueGlobal.get( timeout=(1) ) # 延时，如果收到进程结束信号则立即结束延时
            except:
                pass

            if self.isRun == False:
                print("MeasureUntilSMUsed: Manager Process: isRun = {}, in sleep".format(self.isRun))
                break

        print("MeasureUntilSMUsed: End: Duration = {} s".format(time.time()-tmpTimeStamp))
        sys.stdout.flush()


        return

    def GetTrace(self):
        listPowerTrace = EPOptDrv.GetPowerTrace()
        listSMUtilTrace = EPOptDrv.GetSMUtilTrace()
        listMemUtilTrace = EPOptDrv.GetMemUtilTrace()
        # print("GetTrace: listMemUtilTrace[:20] = {}".format(listMemUtilTrace[:20]))

        self.arrayPowerTrace = np.array(listPowerTrace)
        self.arraySMUtilTrace = np.array(listSMUtilTrace)
        self.arrayMemUtilTrace = np.array(listMemUtilTrace)
        # print("GetTrace: MemUtil = {}".format(self.arrayMemUtilTrace[int(len(self.arrayMemUtilTrace)/2)]))

        #  wfr 这里排除采样序列初始阶段 GPU 还没使用的部分
        self.arrayPowerPctTrace = self.arrayPowerTrace / self.PowerLimit * 100
        tmpBegin = 0

        arraySample0 = self.arrayPowerPctTrace[tmpBegin:] + self.arraySMUtilTrace[tmpBegin:]
        tmpStd0 = np.std(arraySample0)
        arraySample1 = self.arrayPowerPctTrace[tmpBegin:] - self.arraySMUtilTrace[tmpBegin:]
        tmpStd1 = np.std(arraySample1)
        if tmpStd0 > tmpStd1:
            arraySample = arraySample0
        else:
            arraySample = arraySample1
        arraySample0 = arraySample + self.arrayMemUtilTrace[tmpBegin:]
        tmpStd0 = np.std(arraySample0)
        arraySample1 = arraySample - self.arrayMemUtilTrace[tmpBegin:]
        tmpStd1 = np.std(arraySample1)
        if tmpStd0 > tmpStd1:
            arraySample = arraySample0
        else:
            arraySample = arraySample1
        self.arrayCompositeTrace = arraySample / 3

        # self.arrayCompositeTrace = (self.arrayPowerTrace / self.PowerLimit * 100 + self.arraySMUtilTrace + self.arrayMemUtilTrace)/3

        return self.arrayCompositeTrace, self.arrayPowerTrace, self.arraySMUtilTrace, self.arrayMemUtilTrace

    # wfr 20201222 测量直到认为是稳定状态
    def MeasureUntilStable(self, MeasureStateMode, StrictMode = "normal", TPrev = -1, TNextPreference = int(0)):
        global QueueGlobal

        FlagFULL_SIMPLE = True
        FlagIPS_SIMPLE = True

        ZeroTime = 0
        ZeroTimeThreshold = 5

        print("MeasureUntilStable: MeasureStateMode = {}".format(MeasureStateMode))

        if MeasureStateMode == "FULL" or MeasureStateMode == "IPS":
            # 重置频率为 1350MHz
            if isMeasureOverhead == False:
                EPOptDrv.SetEnergyGear(self.BaseGear)
                time.sleep(2)
                EPOptDrv.SetMemClkRange(int(9251), int(9251))
                time.sleep(2) # 延时 1s, 使频率生效且稳定
            # 重置频率调节策略为 驱动默认
            # EPOptDrv.ResetEnergyGear()
            # time.sleep(1) # 延时 1s, 使频率生效且稳定

        if TPrev > 0:
            TEstimated = TPrev
        else:
            TEstimated = 4.0

        self.isStateStable = False
        # wfr 20201228 表示是否一定不稳定, 如果总测量时间远大于测出的周期, 且近几次的周期相差较大, 则认为一定是不稳定的, 此时测量仍然继续, 最后测得的周期作为 近似的固定周期, 即之后使用固定周期
        MustBeUnstable = False
        MeasureMaxFactor = 5.5
        MeasureTFactor = 5.3
        MeasureRedundanceFactor = 0.3
        SumMeasureDuration = 0
        PrevTimeStamp = 0
        MeasureCount = 0
        MeasureDurationNext = self.MeasureDurationInit # 30 # (4+MeasureRedundanceFactor) * TEstimated + 2

        if True == self.IsSMUnusedPeriodly():
            return (0.15 * self.SMUsedDuraiton.value), True


        # 启动测量
        if MeasureStateMode == "SIMPLE":
            EPOptDrv.StartMeasure([], "SIMPLE_FEATURE_TRACE")
        elif MeasureStateMode == "FULL":
            if FlagFULL_SIMPLE == True:
                print("MeasureUntilStable: MeasureStateMode == FULL: use SIMPLE\n")
                EPOptDrv.StartMeasure([], "SIMPLE_FEATURE_TRACE")
            else:
                print("MeasureUntilStable: listMetricGroup[0]: \n{}".format(self.listMetricGroup[0]))
                EPOptDrv.StartMeasure(self.listMetricGroup[0], "FEATURE_TRACE")
        elif MeasureStateMode == "IPS":
            if FlagIPS_SIMPLE == True:
                print("MeasureUntilStable: MeasureStateMode == IPS: use SIMPLE\n")
                EPOptDrv.StartMeasure([], "SIMPLE_FEATURE_TRACE")
            else:
                print("MeasureUntilStable: listMetricIPS: \n{}".format(self.listMetricIPS))
                EPOptDrv.StartMeasure(self.listMetricIPS, "FEATURE_TRACE")
            
        sys.stdout.flush()
        PrevTimeStamp = time.time() # 记录时间戳
        tmpTimeStampStart = time.time()

        listTEstimated = []
        listMeasureDurationNext = []
        # 循环如果: 还不稳定 且 总测量时间没超过上限 且 总测量时间没超过估计周期的5倍
        while self.isStateStable == False and MeasureDurationNext > 0 \
            and SumMeasureDuration < MeasureMaxFactor * self.TUpBoundNew:
            # and SumMeasureDuration < MeasureTFactor * TEstimated:

            MeasureDurationNext = np.max([self.TFixed, MeasureDurationNext])
            # print("MeasureUntilStable: MeasureDurationNext = {0} s".format(MeasureDurationNext))
            # print("MeasureUntilStable: SumMeasureDuration = {0} s".format(SumMeasureDuration))

            # 延时, 这里要减去中间数据处理的时间, 因为测量与数据处理并行, 有时间上的重叠
            tmpDelay = MeasureDurationNext-(time.time()-PrevTimeStamp)
            print("MeasureUntilStable: 延时 {0:.2f} s".format(tmpDelay))
            sys.stdout.flush()
            while tmpDelay > 0:
                tmpTimeStamp = time.time()
                if False == self.TestSMUtil():
                    time.sleep( max(0, 1-(time.time()-tmpTimeStampStart)) )
                    EPOptDrv.StopMeasure()
                    return TEstimated, self.isStateStable
                # 延时, 这里要减去中间数据处理的时间, 因为测量与数据处理并行, 有时间上的重叠
                try:
                    self.isRun = QueueGlobal.get( timeout=(1) ) # 延时，如果收到进程结束信号则立即结束延时
                except:
                    pass
                if self.isRun == False:
                    EPOptDrv.StopMeasure()
                    print("MeasureUntilStable: isRun = {}, in sleep".format(self.isRun))
                    return TEstimated, self.isStateStable

                tmpDelay = tmpDelay - (time.time()-tmpTimeStamp)
            
            print("MeasureUntilStable: 延时 complete")
            sys.stdout.flush()

            # 获得 trace
            EPOptDrv.ReceiveData() # 收数据
            PrevTimeStamp = time.time() # 记录时间戳
            self.arrayCompositeTrace, self.arrayPowerTrace, self.arraySMUtilTrace, self.arrayMemUtilTrace = self.GetTrace() # 读取数据
            # SumMeasureDuration += MeasureDurationNext
            SumMeasureDuration = len(self.arrayCompositeTrace) * self.SampleInterval / 1000
            print("MeasureUntilStable: len of arrayCompositeTrace = {}".format(len(self.arrayCompositeTrace)))

            # 频谱分析判断是否稳定
            if len(self.arrayCompositeTrace) == 0:
                print("MeasureUntilStable WARNING: len of arrayCompositeTrace = 0")
                self.isStateStable = False
                ZeroTime += 1
                if ZeroTime >= ZeroTimeThreshold:
                    self.isRun = False
                    TEstimated = 4.1
                    return TEstimated, self.isStateStable
            else:
                TraceFileName = self.TestPrefix+"-PowerTrace-"+str(self.FileCount)
                print("Before T_SpectrumAnalysis: TPrev = {}; TNextPreference = {}".format(TPrev, TNextPreference))
                TEstimated, self.isStateStable, MeasureDurationNext = T_SpectrumAnalysis(self.arrayCompositeTrace, self.SampleInterval, self.TUpBoundNew, MeasureTFactor, TraceFileName, StrictMode, TPrev, TNextPreference)
                listTEstimated.append(TEstimated)
                listMeasureDurationNext.append(MeasureDurationNext)

                if len(listTEstimated) >= 2:
                    print("listTEstimated = {}".format(listTEstimated))
                    print("listMeasureDurationNext = {}".format(listMeasureDurationNext))
        
        EPOptDrv.StopMeasure()
        print("MeasureUntilStable: EPOptDrv.StopMeasure() has returned")
        self.FileCount += 1
        sys.stdout.flush()
        
        # wfr 20200102 调整周期上限
        if TEstimated < 0.4 * self.TUpBoundNew:
            self.TUpBoundNew = 0.75 * self.TUpBoundNew
        elif TEstimated < 0.75 * self.TUpBoundNew:
            self.TUpBoundNew = 1.2 * self.TUpBoundNew
            self.TUpBoundNew = np.min([self.TUpBound, self.TUpBoundNew])
        print("TUpBoundNew = {0:.2f}".format(self.TUpBoundNew))
        
        if self.isStateStable == True:
            self.MeasureDurationInit = np.max([10, 3 * TEstimated])

        if self.isStateStable == True:
            if MeasureStateMode == "IPS" and FlagIPS_SIMPLE == True:
                TEstimated = self.TimeIncFactor * TEstimated
            elif MeasureStateMode == "FULL" and FlagFULL_SIMPLE == True:
                TEstimated = self.TimeIncFactor * TEstimated
            print("MeasureUntilStable: 周期稳定 TEstimated = {}".format(TEstimated))
        else:
            self.TFixed = TEstimated
            print("MeasureUntilStable: 周期不稳定 TFixed = {}".format(self.TFixed))

        print("MeasureUntilStable: SumMeasureDuration = {}".format(SumMeasureDuration))
        sys.stdout.flush()
        return TEstimated, self.isStateStable

    # wfr 20201222 测量直到认为是不稳定状态
    def MeasureUntilUnstable(self, MeasureStateMode, TRef = -1):
        global QueueGlobal

        if True == self.isStateStable:
            PowerError = 0.18
        else:
            PowerError = 0.3

        ReFullMeasureThreshold = 0.5

        MeasureStateMode = "SIMPLE"
        self.SimpleCount = 0
        self.dequePower = deque([]) # 初始化功率队列
        self.dequeSMUtil = deque([])
        self.dequeMemUtil = deque([])

        print("MeasureUntilUnstable: isStateStable = {0}".format(self.isStateStable))
        if self.isStateStable == False:
            TEstimated = self.TFixed
            time.sleep(1)
        elif self.isStateStable == True:
            TEstimated, self.isStateStable = self.MeasureUntilStable(MeasureStateMode, "relaxed", TRef) # normal
            if self.isStateStable == False or self.isRun == False:
                return self.isStateStable

            tmpLenEnd = len(self.arrayPowerTrace)
            tmpMeasureDuration = (tmpLenEnd - 1) * (self.SampleInterval / 1000)
            tmpMeasureCount = int(np.floor( tmpMeasureDuration / TEstimated ))
            tmpLenT = int( round( TEstimated / (self.SampleInterval/1000) ) ) # 取出最后的 TEstimated 时间内的 采样数据
            for i in range(tmpMeasureCount-1):
                tmpIndexBegin = tmpLenEnd - (i+1) * tmpLenT - 1
                tmpIndexEnd = tmpLenEnd - (i) * tmpLenT

                array0 = np.array(self.arrayPowerTrace[tmpIndexBegin:tmpIndexEnd])
                tmpPower = np.mean(array0) - self.PowerThreshold # 平均功率
                if len(self.dequePower) != 2:
                    self.dequePower.append(tmpPower) # init min power
                    self.dequePower.append(tmpPower) # init max power
                else:
                    if tmpPower < self.dequePower[0]:
                        self.dequePower[0] = tmpPower
                    elif tmpPower > self.dequePower[1]:
                        self.dequePower[1] = tmpPower

                array0 = np.array(self.arraySMUtilTrace[tmpIndexBegin:tmpIndexEnd])
                tmpSMUtil = np.mean(array0) # 平均占用率
                if len(self.dequeSMUtil) != 2:
                    self.dequeSMUtil.append(tmpSMUtil) # init min power
                    self.dequeSMUtil.append(tmpSMUtil) # init max power
                else:
                    if tmpSMUtil < self.dequeSMUtil[0]:
                        self.dequeSMUtil[0] = tmpSMUtil
                    elif tmpSMUtil > self.dequeSMUtil[1]:
                        self.dequeSMUtil[1] = tmpSMUtil

                array0 = np.array(self.arrayMemUtilTrace[tmpIndexBegin:tmpIndexEnd])
                tmpMemUtil = np.mean(array0) # 平均占用率
                if len(self.dequeMemUtil) != 2:
                    self.dequeMemUtil.append(tmpMemUtil) # init min power
                    self.dequeMemUtil.append(tmpMemUtil) # init max power
                else:
                    if tmpMemUtil < self.dequeMemUtil[0]:
                        self.dequeMemUtil[0] = tmpMemUtil
                    elif tmpMemUtil > self.dequeMemUtil[1]:
                        self.dequeMemUtil[1] = tmpMemUtil

            self.SimpleCount += tmpMeasureCount-1

        if False == self.TestSMUtil():
            self.isStateStable = False
            return self.isStateStable

        sys.stdout.flush()
        while True:
            EPOptDrv.StartMeasure([], "SIMPLE_FEATURE_TRACE")
            tmpTimeStampStart = time.time()

            tmpDelay = TEstimated + 1
            print("MeasureUntilStable: 延时 {0:.2f} s".format(tmpDelay))
            sys.stdout.flush()
            while tmpDelay > 0:
                tmpTimeStamp = time.time()
                if False == self.TestSMUtil():
                    time.sleep( max(0, 1-(time.time()-tmpTimeStampStart)) )
                    EPOptDrv.StopMeasure()
                    self.isStateStable = False
                    return self.isStateStable
                # 延时, 这里要减去中间数据处理的时间, 因为测量与数据处理并行, 有时间上的重叠
                try:
                    self.isRun = QueueGlobal.get( timeout=(0.2) ) # 延时，如果收到进程结束信号则立即结束延时
                except:
                    pass
                if self.isRun == False:
                    EPOptDrv.StopMeasure()
                    print("MeasureUntilStable: isRun = {}, in sleep".format(self.isRun))
                    self.isStateStable = False
                    return self.isStateStable

                tmpDelay = tmpDelay - (time.time()-tmpTimeStamp)

            EPOptDrv.StopMeasure()
            print("MeasureUntilUnstable: self.GetTrace()")
            self.arrayCompositeTrace, self.arrayPowerTrace, self.arraySMUtilTrace, self.arrayMemUtilTrace = self.GetTrace() # 读取数据
            print("MeasureUntilUnstable: len of arrayPowerTrace = {}".format(len(self.arrayPowerTrace)))
            # print("arrayPowerTrace: {}".format(self.arrayPowerTrace))
            sys.stdout.flush()
            
            tmpLenT = int( round( TEstimated / (self.SampleInterval/1000) ) ) # 取出最后的 TEstimated 时间内的采样点
            tmpLenEnd = len(self.arrayPowerTrace)

            dictFeature = {"Energy": 1e5, "Time": self.TUpBound, "Power": 1e5 / self.TUpBound, "SMUtil": 100, "MemUtil": 100}
            if tmpLenEnd > tmpLenT:
                tmpIndexBegin = tmpLenEnd - tmpLenT
                tmpIndexEnd = tmpLenEnd
                # print("tmpIndexBegin = {}; tmpIndexEnd = {}".format(tmpIndexBegin, tmpIndexEnd))
                array0 = np.array(self.arrayPowerTrace[tmpIndexBegin:tmpIndexEnd])
                dictFeature["Power"] = np.mean(array0) - self.PowerThreshold # 平均功率
                dictFeature["Time"] = TEstimated
                dictFeature["Energy"] = dictFeature["Power"] * dictFeature["Time"]
                array0 = np.array(self.arraySMUtilTrace[tmpIndexBegin:tmpIndexEnd])
                dictFeature["SMUtil"] = np.mean(array0)
                array0 = np.array(self.arrayMemUtilTrace[tmpIndexBegin:tmpIndexEnd])
                dictFeature["MemUtil"] = np.mean(array0)
            else:
                dictFeature = EPOptDrv.GetFeature() # 读取数据
                print("MeasureUntilUnstable: dictFeature:")
                print(dictFeature)
                # dictFeature["Power"] = dictFeature["Energy"] / np.max([1e-9, dictFeature["Time"]])

            self.SimpleCount += 1
            sys.stdout.flush()
            
            # 如果是首次 简测量，就 清空队列 再 保存第一次的 PowerSimple 既为最小值也为最大值
            # dequePower[0] 保存最小值，dequePower[1] 保存最大值
            if len(self.dequePower) != 2:
                self.dequePower.clear()
                self.dequePower.append(dictFeature["Power"])
                self.dequePower.append(dictFeature["Power"])
            else:
                if dictFeature["Power"] < self.dequePower[0]:
                    self.dequePower[0] = dictFeature["Power"]
                elif dictFeature["Power"] > self.dequePower[1]:
                    self.dequePower[1] = dictFeature["Power"]
            minPower = min(self.dequePower)
            maxPower = max(self.dequePower)
            meanPower = sum(self.dequePower) / len(self.dequePower)

            if len(self.dequeSMUtil) != 2:
                self.dequeSMUtil.clear()
                self.dequeSMUtil.append(dictFeature["SMUtil"])
                self.dequeSMUtil.append(dictFeature["SMUtil"])
            else:
                if dictFeature["SMUtil"] < self.dequeSMUtil[0]:
                    self.dequeSMUtil[0] = dictFeature["SMUtil"]
                elif dictFeature["SMUtil"] > self.dequeSMUtil[1]:
                    self.dequeSMUtil[1] = dictFeature["SMUtil"]
            minSMUtil = min(self.dequeSMUtil)
            maxSMUtil = max(self.dequeSMUtil)
            meanSMUtil = sum(self.dequeSMUtil) / len(self.dequeSMUtil)

            if len(self.dequeMemUtil) != 2:
                self.dequeMemUtil.clear()
                self.dequeMemUtil.append(dictFeature["MemUtil"])
                self.dequeMemUtil.append(dictFeature["MemUtil"])
            else:
                if dictFeature["MemUtil"] < self.dequeMemUtil[0]:
                    self.dequeMemUtil[0] = dictFeature["MemUtil"]
                elif dictFeature["MemUtil"] > self.dequeMemUtil[1]:
                    self.dequeMemUtil[1] = dictFeature["MemUtil"]
            minMemUtil = min(self.dequeMemUtil)
            maxMemUtil = max(self.dequeMemUtil)
            meanMemUtil = sum(self.dequeMemUtil) / len(self.dequeMemUtil)

            print("tmpPower = {}".format(dictFeature["Power"]))
            print("tmpSMUtil = {}".format(dictFeature["SMUtil"]))
            print("tmpMemUtil = {}".format(dictFeature["MemUtil"]))
            sys.stdout.flush()

            # 偏差过大则认为应用运行进入不稳定状态
            if abs((maxPower-minPower)/meanPower) > PowerError:
            # if abs((maxPower-minPower)/meanPower) > PowerError \
            #     or abs((maxSMUtil-minSMUtil)/meanSMUtil) > PowerError \
            #     or abs((maxMemUtil-minMemUtil)/meanMemUtil) > PowerError:
                
                if True == self.IsSMUnusedPeriodly():
                    pass
                elif abs((maxPower-minPower)/meanPower) < ReFullMeasureThreshold:
                    self.PredictedOptGear.value = self.SearchedOptGear.value
                    self.SearchedOptGear.value = int(-1)
                    self.PredictedOptMemClk.value = int(self.SearchedOptMemClk.value)
                    self.SearchedOptMemClk.value = int(-1)
                    self.LocalSearchState = "RESTART"
                else:
                    self.PredictedOptGear.value = int(-1)
                    self.SearchedOptGear.value = int(-1)
                    self.PredictedOptMemClk.value = int(-1)
                    self.SearchedOptMemClk.value = int(-1)
                    self.LocalSearchState = "RESTART"

                self.SimpleCount = int(0)
                self.isStateStable = False
                print("MeasureUntilUnstable: dequePower: {}".format(self.dequePower))
                print("MeasureUntilUnstable: dequeSMUtil: {}".format(self.dequeSMUtil))
                print("MeasureUntilUnstable: dequeMemUtil: {}".format(self.dequeMemUtil))
                print("MeasureUntilUnstable: 进入不稳定状态")
                sys.stdout.flush()
                return self.isStateStable

            # 多次简测量, 应用都是稳定状态, 则 休眠一段时间
            elif self.SimpleCount >= 3:
                print("MeasureUntilUnstable: 仍是稳定状态")
                NumInterval = pow(2, self.SimpleCount-1) # 指数增加 测量间隔
                NumInterval = min(NumInterval, 32) # 间隔数量上限是 32 个测量持续时间

                tmpDelay = NumInterval * TEstimated
                print("MeasureUntilStable: 延时 {0:.2f} s".format(tmpDelay))
                sys.stdout.flush()
                while tmpDelay > 0:
                    tmpTimeStamp = time.time()
                    if False == self.TestSMUtil():
                        self.isStateStable = False
                        return self.isStateStable
                    # 延时, 这里要减去中间数据处理的时间, 因为测量与数据处理并行, 有时间上的重叠
                    try:
                        self.isRun = QueueGlobal.get( timeout=(1) ) # 延时，如果收到进程结束信号则立即结束延时
                    except:
                        pass
                    if self.isRun == False:
                        print("MeasureUntilStable: isRun = {}, in sleep".format(self.isRun))
                        self.isStateStable = False
                        return self.isStateStable

                    tmpDelay = tmpDelay - (time.time()-tmpTimeStamp)

            sys.stdout.flush()
        self.isStateStable = False
        return self.isStateStable

    def MeasureFeature(self, MeasureStateMode, IsTryDetectPeriod=True, StrictMode = "normal", TPrev = -1, TNextPreference = int(0)):
        global QueueGlobal

        print("\nMeasureFeature: MeasureStateMode = {}".format(MeasureStateMode))

        dictFeature = {"Energy": 1e5, "Time": self.TUpBound, "Power": 1e5 / self.TUpBound, "SMUtil": 100, "MemUtil": 100}

        if MeasureStateMode == "FULL":
            # 重置频率为 1350 MHz
            if isMeasureOverhead == False:
                EPOptDrv.SetEnergyGear(self.BaseGear)
                time.sleep(2)
                EPOptDrv.SetMemClkRange(int(9251), int(9251))
                time.sleep(2) # 延时 1s, 使频率生效且稳定
        elif MeasureStateMode == "IPS":
            dictFeature["sm__inst_executed.sum.per_second"] = 1
            dictFeature["sm__inst_executed.sum"] = dictFeature["sm__inst_executed.sum.per_second"] * dictFeature["Time"]

        if IsTryDetectPeriod == True:
            TEstimated, self.isStateStable = self.MeasureUntilStable(MeasureStateMode, StrictMode, TPrev, TNextPreference)
        else:
            if StrictMode == "external":
                TEstimated = TPrev
                print("MeasureFeature: 使用外部周期; TEstimated = {}".format(TEstimated))
            else:
                TEstimated = self.TFixed
                print("MeasureFeature: 使用固定周期; TEstimated = {}".format(TEstimated))

        dictFeature["Time"] = TEstimated

        if self.isRun == False:
            print("Manager Process: isRun = {}, in sleep".format(self.isRun))
            dictFeature["Power"] = dictFeature["Power"] - self.PowerThreshold
            dictFeature["Energy"] = dictFeature["Power"] * dictFeature["Time"]
            return dictFeature, TEstimated

        sys.stdout.flush()

        if MeasureStateMode == "SIMPLE":
            tmpNumT = 2
            if IsTryDetectPeriod == False:
                EPOptDrv.StartMeasure([], "SIMPLE_FEATURE_TRACE")
                tmpTimeStampStart = time.time()
                
                tmpDelay = tmpNumT * TEstimated
                print("MeasureUntilStable: 延时 {0:.2f} s".format(tmpDelay))
                sys.stdout.flush()
                while tmpDelay > 0:
                    tmpTimeStamp = time.time()
                    if False == self.TestSMUtil():
                        time.sleep( max(0, 1-(time.time()-tmpTimeStampStart)) )
                        EPOptDrv.StopMeasure()
                        dictFeature["Power"] = dictFeature["Power"] - self.PowerThreshold
                        dictFeature["Energy"] = dictFeature["Power"] * dictFeature["Time"]
                        return dictFeature, TEstimated
                    # 延时, 这里要减去中间数据处理的时间, 因为测量与数据处理并行, 有时间上的重叠
                    try:
                        self.isRun = QueueGlobal.get( timeout=(0.2) ) # 延时，如果收到进程结束信号则立即结束延时
                    except:
                        pass
                    if self.isRun == False:
                        EPOptDrv.StopMeasure()
                        print("MeasureUntilStable: isRun = {}, in sleep".format(self.isRun))
                        dictFeature["Power"] = dictFeature["Power"] - self.PowerThreshold
                        dictFeature["Energy"] = dictFeature["Power"] * dictFeature["Time"]
                        return dictFeature, TEstimated

                    tmpDelay = tmpDelay - (time.time()-tmpTimeStamp)

                EPOptDrv.StopMeasure()
                print("MeasureFeature: self.GetTrace()")
                self.arrayCompositeTrace, self.arrayPowerTrace, self.arraySMUtilTrace, self.arrayMemUtilTrace = self.GetTrace() # 读取数据
                print("MeasureFeature: len of arrayCompositeTrace = {}".format(len(self.arrayCompositeTrace)))
            sys.stdout.flush()
            # 从 self.arrayCompositeTrace 中取出最后一个 TEstimated 的数据计算特征
            dictFeature["Time"] = TEstimated
            tmpLenEnd = len(self.arrayCompositeTrace)
            tmpLenT = tmpNumT * int( round( TEstimated / (self.SampleInterval/1000) ) ) # 取出最后的 2个 TEstimated 时间内的 采样数据
            tmpLenT = min(tmpLenT, (tmpLenEnd-2))

            array0 = np.array(self.arrayPowerTrace[(tmpLenEnd-tmpLenT-1):tmpLenEnd])
            array1 = np.array(self.arrayPowerTrace[(tmpLenEnd-tmpLenT-2):tmpLenEnd-1])
            dictFeature["Power"] = np.mean(array0 + array1)/tmpNumT - self.PowerThreshold # 平均功率 (用一阶线性插值减小误差)
            dictFeature["Energy"] = dictFeature["Power"] * dictFeature["Time"] # 平均功率 * 时间

            array0 = np.array(self.arraySMUtilTrace[(tmpLenEnd-tmpLenT-1):tmpLenEnd])
            array1 = np.array(self.arraySMUtilTrace[(tmpLenEnd-tmpLenT-2):tmpLenEnd-1])
            dictFeature["SMUtil"] = np.mean(array0 + array1)/tmpNumT

            array0 = np.array(self.arrayMemUtilTrace[(tmpLenEnd-tmpLenT-1):tmpLenEnd])
            array1 = np.array(self.arrayMemUtilTrace[(tmpLenEnd-tmpLenT-2):tmpLenEnd-1])
            dictFeature["MemUtil"] = np.mean(array0 + array1)/tmpNumT
        
        elif MeasureStateMode == "FULL":
            # 这里需要高精度测量, 所以在 C++级别 定时
            # wfr 20210213 使用 C++级别 定时 的劣势是: 定时过程中不能被 python 级别的信号打断, 即不能提前结束

            sumEnergy = 0.0
            sumTime = 0.0
            sumPower = 0.0
            sumSMUtil = 0.0
            sumMemUtil = 0.0
            for i in range(len(self.listMetricGroup)):
                EPOptDrv.MeasureDuration(self.listMetricGroup[i], "FEATURE", TEstimated)
                tmpDictFeature = EPOptDrv.GetFeature() # 读取数据
                sumEnergy += tmpDictFeature["Energy"]
                sumTime += tmpDictFeature["Time"]
                sumPower += tmpDictFeature["Power"]
                sumSMUtil += tmpDictFeature["SMUtil"]
                sumMemUtil += tmpDictFeature["MemUtil"]
                del tmpDictFeature["Energy"]
                del tmpDictFeature["Time"]
                del tmpDictFeature["Power"]
                del tmpDictFeature["SMUtil"]
                del tmpDictFeature["MemUtil"]
                dictFeature.update(tmpDictFeature)
                # wfr 20210825 if SMUtil == 0, no more measurements
                if False == self.TestSMUtil():
                    break
            
            dictFeature["Time"] = sumTime / len(self.listMetricGroup)
            dictFeature["Power"] = sumPower / len(self.listMetricGroup) - self.PowerThreshold
            dictFeature["Energy"] = dictFeature["Power"] * dictFeature["Time"]
            dictFeature["SMUtil"] = sumSMUtil / len(self.listMetricGroup)
            dictFeature["MemUtil"] = sumMemUtil / len(self.listMetricGroup)

            EPOptDrv.ResetMemClkRange()

        elif MeasureStateMode == "IPS":

            # wfr 20210825 if SMUtil != 0, then measure
            if True == self.TestSMUtil():
                print("self.listMetricIPS:")
                print(self.listMetricIPS)
                print("TEstimated = {}".format(TEstimated))
                EPOptDrv.MeasureDuration(self.listMetricIPS, "FEATURE", TEstimated)
                dictFeature = EPOptDrv.GetFeature() # 读取数据

            dictFeature["Time"] = self.TimeDecFactor * dictFeature["Time"]
            dictFeature["Power"] = self.EngDecFactor * dictFeature["Power"] - self.PowerThreshold
            dictFeature["Energy"] = dictFeature["Power"] * dictFeature["Time"]
            dictFeature["sm__inst_executed.sum.per_second"] = self.IPSIncFactor * dictFeature["sm__inst_executed.sum.per_second"]
            dictFeature["sm__inst_executed.sum"] = self.IPSIncFactor * dictFeature["sm__inst_executed.sum"]

            # wfr 20211010 打印输出 SM 占用比相关数据
            if "sm__cycles_active.avg" in dictFeature.keys():
                if dictFeature["sm__cycles_active.avg"] < 1e-3:
                    dictFeature["sm__cycles_active.avg"] = 1e10
                if dictFeature["sm__cycles_elapsed.avg"] < 1e-3:
                    dictFeature["sm__cycles_elapsed.avg"] = 1e13
                SMActCycPct = dictFeature["sm__cycles_active.avg"] / dictFeature["sm__cycles_elapsed.avg"]
                IPSAct = dictFeature["sm__inst_executed.sum.per_second"] / SMActCycPct
                print("MeasureFeature IPS: SMActCycPct = {} %".format(SMActCycPct *100))
                print("MeasureFeature IPS: IPSAct = {}".format(IPSAct))

        sys.stdout.flush()
        # 检查是否停止运行
        try:
            self.isRun = QueueGlobal.get(block = False)
        except:
            pass
        if self.isRun == False:
            print("Manager Process: isRun = {}".format(self.isRun))

        return dictFeature, TEstimated

    def Init(self):

        self.isInit = EPOptDrv.ManagerInit(self.DeviceIDNVML, self.RunMode, self.MEASURE_STOP_MODE["SIGNAL"])
        print("ManagerInit = {:d}".format(self.isInit))
        if self.isInit < 0:
            return

        self.SMClkGearCount = int(EPOptDrv.GetSMClkGearCount() ) # 0, 1, 2, ..., SMClkGearCount-1
        self.SMClkGearCount = 120
        self.NumGears = self.SMClkGearCount

        self.BaseSMClk = int(EPOptDrv.GetBaseSMClk())
        self.BaseSMClk = 1800
        self.MinSMClk= int(EPOptDrv.GetMinSMClk())
        self.SMClkStep = int(EPOptDrv.GetSMClkStep())
        self.GPUName = EPOptDrv.GetGPUName()
        self.GPUName = self.GPUName.replace("NVIDIA","").replace("GeForce","").replace(" ","")
        self.BaseGear = int((self.BaseSMClk - self.MinSMClk) / self.SMClkStep)
        self.PowerLimit = EPOptDrv.GetPowerLimit()
        if self.GPUName == "RTX3080Ti":
            self.PowerThreshold = 30.0
        elif self.GPUName == "RTX2080Ti":
            self.PowerThreshold = 1.65
        else:
            self.PowerThreshold = 0.0

        print("MinSMClk = {:d}; BaseSMClk = {:d}; SMClkStep = {:d}".format(self.MinSMClk, self.BaseSMClk, self.SMClkStep))
        print("SMClkGearCount = {:d}; BaseGear = {:d}".format(self.SMClkGearCount, self.BaseGear))

        if self.SMClkGearCount <= 0:
            print("EPOpt ERROR: 获得 SMClkGearCount 错误")
            os._exit(0)

    def LearnMode(self):
        return

    def WorkMode(self):
        print("WorkMode: in: sleep(3)")
        global QueueGlobal
        time.sleep(3)

        from EPOptXGBoost import EP_OPT_XGBOOST
        EPOptXGB = EP_OPT_XGBOOST()

        if self.Obj == "Energy":
            self.Threshold = self.PerfLoss
            print("WorkMode: self.PerfLoss = {}".format(self.PerfLoss))
        elif self.Obj == "Performance":
            self.Threshold = self.EngSave
            print("WorkMode: self.EngSave = {}".format(self.EngSave))
        else:
            self.Threshold = -1.0

        EPOptXGB.Init(self.ModelDir, self.GPUName)

        self.CurrentGear.value = self.NumGears

        TSimple = 0
        TFull = 0

        print("WorkMode: 开始工作模式")
        print("WatchSMUsed0: SMUtilTolerateFlag = {}".format(self.SMUtilTolerateFlag.value))
        strIPS = "sm__inst_executed.sum.per_second"
        strInst = "sm__inst_executed.sum"

        self.PredictedOptGear.value = int(-1)
        self.SearchedOptGear.value = int(-1)
        self.PredictedOptMemClk.value = int(-1)
        self.SearchedOptMemClk.value = int(-1)
        while True:
            # wfr init isStateStable as True
            # if isStateStable is True, current loop is periodic, need detect period when gear changed, use runtime(T) as performace metric
            # if isStateStable is False, current loop is non-periodic, do not detect and use fixed peirod, use IPS as performace metric
            self.isStateStable = True
            self.ResetTRange()
            
            self.MeasureUntilSMUsed()
            if self.isRun == False:
                return

            # wfr 20211110 如果有较长时间没有使用 GPU, 则不再进行常规的优化过程
            # 而是使用指定的 频率配置
            if self.SMUsedDuraiton.value > 6 and self.SMUnusedDuraiton.value > 6 and self.SMUnusedDuraiton.value / self.SMUsedDuraiton.value > 0.2:
                self.PredictedOptGear.value = int(106)
                self.SearchedOptGear.value = int(106)
                self.PredictedOptMemClk.value = int(9251)
                self.SearchedOptMemClk.value = int(9251)

            if self.PredictedOptGear.value < 0:

                TimeStamp("Begin Predict")
                print("Begin Predict")

                # 进行全测量, 测量 dictFeature
                print("WorkMode: 全测量")
                self.dictFeature, TFull = self.MeasureFeature("FULL", True, StrictMode = "strict")
                if self.isRun == False:
                    return
                if False == self.TestSMUtil():
                    continue
                self.SaveTPrev(TFull, self.BaseGear)
                
                # wfr 20210710 StateStable should be the same in one while loop
                if TFull > 30: # 周期较大时强制指定使用 IPS 指标
                    self.isStateStable = False
                TSimple = TFull / self.TimeIncFactor
                if self.isStateStable == False:
                    TFull = max(TFull, 4)

                localStateStable = self.isStateStable
                print("dictFeature:")
                print(self.dictFeature)
                if "sm__inst_executed_pipe_cbu.sum.pct_of_peak_sustained_active" not in self.dictFeature.keys():
                    print("ERROR: sm__inst_executed_pipe_cbu.sum.pct_of_peak_sustained_active")
                    continue

                # 检查是否停止运行
                if self.isRun == False:
                    return
                # 检查是否停止运行
                try:
                    self.isRun = QueueGlobal.get(block = False)
                except:
                    pass
                if self.isRun == False:
                    print("Manager Process: isRun = {}".format(self.isRun))
                    return


                ConstraintDefault = 1.0
                RewardDefault = 1.0
                if (self.Obj == "Energy" or self.Obj == "Performance") and True == localStateStable:
                    EPOptDrv.ResetEnergyGear()
                    time.sleep(2)
                    EPOptDrv.ResetMemClkRange()
                    time.sleep(2)

                    print("WorkMode: 简测量 默认配置")
                    dictFeatureDefault, TSimple = self.MeasureFeature("SIMPLE", True, StrictMode = "relaxed")
                    if self.isRun == False:
                        return
                    if False == self.TestSMUtil():
                        continue
                    if self.Obj == "Energy":
                        RewardDefault = dictFeatureDefault["Energy"] * dictFeatureDefault["Time"]**2
                        ConstraintDefault = dictFeatureDefault["Time"]
                    elif self.Obj == "Performance":
                        RewardDefault = dictFeatureDefault["Time"]
                        ConstraintDefault = dictFeatureDefault["Energy"]

                elif self.Obj == "Energy" or self.Obj == "Performance":
                    EPOptDrv.ResetEnergyGear()
                    time.sleep(2)
                    EPOptDrv.ResetMemClkRange()
                    time.sleep(2)

                    print("WorkMode: 测量 默认配置 IPS")
                    # dictFeatureDefault, TSimple = self.MeasureFeature("IPS", localStateStable, StrictMode = "normal")
                    dictFeatureDefault, TSimple = self.MeasureFeature("IPS", False, "external", TFull)
                    if self.isRun == False:
                        return
                    if False == self.TestSMUtil():
                        continue
                    if self.Obj == "Energy":
                        NumInst = 1e13
                        IPSScale = 1e10 # IPS 的调节系数
                        PowerScale = 1
                        RewardScale = 10
                        IPSActive = dictFeatureDefault["sm__inst_executed.sum.per_second"]
                        RewardDefault = RewardScale / ( pow( IPSActive / IPSScale, 3 ) / ( (dictFeatureDefault["Energy"] / dictFeatureDefault["Time"]) * PowerScale ) )
                        ConstraintDefault = NumInst / IPSActive
                    elif self.Obj == "Performance":
                        NumInst = 1e13
                        IPSActive = dictFeatureDefault["sm__inst_executed.sum.per_second"]
                        RewardDefault = NumInst / IPSActive
                        ConstraintDefault = NumInst * dictFeatureDefault["Energy"] / dictFeatureDefault["sm__inst_executed.sum"]

                print("RewardDefault = {}".format(RewardDefault))
                print("dictFeatureDefault:")
                print(dictFeatureDefault)


                # wfr 20210628 predict energy and time
                # ClockLowerBound = 390 # 2080Ti
                ClockLowerBound = 450 # 3080Ti
                tmpGearBegin = int((ClockLowerBound - self.MinSMClk) / self.SMClkStep)
                print("Predict: tmpGearBegin = {}".format(tmpGearBegin))
                arrayGear = np.arange(tmpGearBegin, self.NumGears, 1).astype(int)
                arrayClock = (self.MinSMClk + self.SMClkStep * arrayGear).astype(int)
                PredictedEnergy, PredictedTime, PredictedEnergyMem, PredictedTimeMem = EPOptXGB.Predict(self.dictFeature, arrayClock, self.BaseSMClk, self.arrayMemClk, self.MemClkBase)
                PredictedReward, PredictedConstraint = GetArrayReward(PredictedEnergy, PredictedTime, self.Obj, 1.0)
                PredictedRewardMem, PredictedConstraintMem = GetArrayReward(PredictedEnergyMem, PredictedTimeMem, self.Obj, 1.0)

                self.PredictedOptGear.value = SelectOptGear(arrayGear, PredictedReward, PredictedConstraint, self.Obj, self.Threshold)
                tmpIndex = np.argwhere(arrayGear == self.PredictedOptGear.value).flatten()[0]
                self.PredictedOptReward = PredictedReward[tmpIndex]

                self.PredictedOptMemClk.value = int(SelectOptGear(self.arrayMemClk, PredictedRewardMem, PredictedConstraintMem, self.Obj, self.Threshold))
                tmpIndex = np.argwhere(self.arrayMemClk == self.PredictedOptMemClk.value).flatten()[0]
                self.PredictedOptRewardMem = PredictedRewardMem[tmpIndex]

                print("Optimization Object: {}".format(self.Obj))
                print("WorkMode: Predicted Opt SM Gear = {}".format(self.PredictedOptGear.value))
                print("WorkMode: Predicted Opt Mem Clock = {}".format(self.PredictedOptMemClk.value))
                sys.stdout.flush()
                

            if True == self.IsSMUnusedPeriodly():
                self.SearchedOptGear.value = self.PredictedOptGear.value
                self.SearchedOptMemClk.value = int(self.PredictedOptMemClk.value)

            if isMeasureOverhead == True:
                self.PredictedOptGear.value = self.BaseGear

            # wfr 20211031 对 显存频率 进行局部搜索
            if self.SearchedOptMemClk.value < 0:
                TimeStamp("Begin Local Search For Memory Clock")
                print("Begin Local Search For Memory Clock")

                AllTryCount = 0
                arrayReward = -1 * np.ones(len(self.arrayMemClk))
                arrayConstraint = -1 * np.ones(len(self.arrayMemClk))
                arrayIPS = -1 * np.ones(len(self.arrayMemClk))
                arrayEng = -1 * np.ones(len(self.arrayMemClk))
                arrayInst = -1 * np.ones(len(self.arrayMemClk))
                arrayTime = -1 * np.ones(len(self.arrayMemClk))
                
                # 先设置 SearchedOptGear
                self.CurrentGear.value = self.PredictedOptGear.value
                print("Set CurrentGear = {:d}".format(self.CurrentGear.value))
                if isMeasureOverhead == False:
                    EPOptDrv.SetEnergyGear(self.CurrentGear.value)
                    time.sleep(2) # 延时 1s, 使频率生效且稳定

                # 设置并测量 SearchedOptMemClk 的数据
                self.CurrentMemClk.value = int(self.PredictedOptMemClk.value)
                self.CurrentMemClkIndex = np.argwhere(int(self.CurrentMemClk.value) == self.arrayMemClk).flatten()[0]
                self.OptMemClkIndex = self.CurrentMemClkIndex
                if isMeasureOverhead == False:
                    EPOptDrv.SetMemClkRange(int(self.CurrentMemClk.value), int(self.CurrentMemClk.value))
                    time.sleep(2) # 延时 1s, 使频率生效且稳定

                if localStateStable == True:
                    print("WorkMode: 简测量 PredictedOptMemClk = {}".format(self.CurrentMemClk.value))
                    self.dictFeature, TSimple = self.MeasureFeature("SIMPLE", localStateStable, "relaxed")
                    if self.isRun == False:
                        return
                    arrayEng[self.CurrentMemClkIndex] = self.dictFeature["Energy"]
                    arrayTime[self.CurrentMemClkIndex] = self.dictFeature["Time"]
                else:
                    print("WorkMode: 测量 IPS PredictedOptMemClk = {}".format(self.CurrentMemClk.value))
                    # self.dictFeature, TSimple = self.MeasureFeature("IPS", localStateStable, StrictMode = "normal")
                    self.dictFeature, TSimple = self.MeasureFeature("IPS", False, "external", TFull*PredictedTimeMem[self.CurrentMemClkIndex])
                    if self.isRun == False:
                        return
                    arrayIPS[self.CurrentMemClkIndex] = self.dictFeature[strIPS]
                    arrayInst[self.CurrentMemClkIndex] = self.dictFeature[strInst]
                    arrayEng[self.CurrentMemClkIndex] = self.dictFeature["Energy"]
                    arrayTime[self.CurrentMemClkIndex] = self.dictFeature["Time"]
                if False == self.TestSMUtil():
                    continue
                print("dictFeature:")
                print(self.dictFeature)

                arrayReward[self.CurrentMemClkIndex], arrayConstraint[self.CurrentMemClkIndex] = GetReward(self.dictFeature, self.Obj, localStateStable, ConstraintDefault)

                # wfr 20211101 构建备选内存频率 的 index 的 列表
                if arrayConstraint[self.CurrentMemClkIndex] < 1.2 * self.Threshold:
                    if self.CurrentMemClkIndex == len(self.arrayMemClk) - 1:
                        arrayCandidate = np.array([self.CurrentMemClkIndex-1, self.CurrentMemClkIndex-2])
                    elif self.CurrentMemClkIndex == 0:
                        arrayCandidate = np.array([2, 1])
                    else:
                        arrayCandidate = np.array([self.CurrentMemClkIndex+1, self.CurrentMemClkIndex-1])
                else:
                    tmpLen = len(self.arrayMemClk) - self.CurrentMemClkIndex - 1
                    tmpLen = min(2, tmpLen)
                    arrayCandidate = np.arange(self.CurrentMemClkIndex + 1 , self.CurrentMemClkIndex + tmpLen + 1, 1).astype(int)
                    tmpIndex = np.argsort(-1 * arrayCandidate)
                    arrayCandidate = arrayCandidate[tmpIndex]
                print("WorkMode: arrayMemClkIndexCandidate = {}".format(arrayCandidate))

                # wfr 20211101 尝试/测量/评价 备选内存频率
                for Candidate in arrayCandidate:
                    if arrayReward[Candidate] > 0:
                        continue

                    self.CurrentMemClkIndex = Candidate
                    self.CurrentMemClk.value = int(self.arrayMemClk[Candidate])
                    if isMeasureOverhead == False:
                        EPOptDrv.SetMemClkRange(int(self.CurrentMemClk.value), int(self.CurrentMemClk.value))
                        time.sleep(4) # 延时 1s, 使频率生效且稳定
                    
                    if localStateStable == True:
                        print("WorkMode: 简测量 Candidate MemClk = {}".format(self.CurrentMemClk.value))
                        self.dictFeature, TSimple = self.MeasureFeature("SIMPLE", localStateStable, "relaxed")
                        if self.isRun == False:
                            return
                        arrayEng[self.CurrentMemClkIndex] = self.dictFeature["Energy"]
                        arrayTime[self.CurrentMemClkIndex] = self.dictFeature["Time"]
                    else:
                        print("WorkMode: 测量 IPS Candidate MemClk = {}".format(self.CurrentMemClk.value))
                        # self.dictFeature, TSimple = self.MeasureFeature("IPS", localStateStable, StrictMode = "normal")
                        self.dictFeature, TSimple = self.MeasureFeature("IPS", False, "external", TFull*PredictedTimeMem[self.CurrentMemClkIndex])
                        if self.isRun == False:
                            return
                        arrayIPS[self.CurrentMemClkIndex] = self.dictFeature[strIPS]
                        arrayInst[self.CurrentMemClkIndex] = self.dictFeature[strInst]
                        arrayEng[self.CurrentMemClkIndex] = self.dictFeature["Energy"]
                        arrayTime[self.CurrentMemClkIndex] = self.dictFeature["Time"]
                    if False == self.TestSMUtil():
                        continue
                    print("dictFeature:")
                    print(self.dictFeature)

                    arrayReward[self.CurrentMemClkIndex], arrayConstraint[self.CurrentMemClkIndex] = GetReward(self.dictFeature, self.Obj, localStateStable, ConstraintDefault)

                    # 如果较高频率都不满足约束条件, 则不再继续尝试其他频率
                    if 0.9 * (1 + arrayConstraint[self.CurrentMemClkIndex]) -1 > self.Threshold:
                        print("WorkMode: 较高内存频率不满足性能损失约束, 跳出局部搜素")
                        break

                    if False and arrayReward[self.CurrentMemClkIndex ] / RewardDefault < 0.65:
                        print("WorkMode: 当前内存频率节能效果较好, 跳出局部搜素")
                        break

                tmpIndex = np.argwhere(arrayReward > 0).flatten()
                self.SearchedOptMemClk.value = int(SelectOptGear(self.arrayMemClk[tmpIndex], arrayReward[tmpIndex], arrayConstraint[tmpIndex], self.Obj, self.Threshold))


            # wfr 20211101 设置最优的内存频率
            if self.SearchedOptMemClk.value > 0:
                self.CurrentMemClk.value = int(self.SearchedOptMemClk.value)
            elif self.PredictedOptMemClk.value > 0:
                self.CurrentMemClk.value = int(self.PredictedOptMemClk.value)
            else: 
                self.CurrentMemClk.value = int(9251)
            if isMeasureOverhead == False:
                EPOptDrv.SetMemClkRange(int(self.CurrentMemClk.value), int(self.CurrentMemClk.value))

            if self.SearchedOptGear.value < 0:

                TimeStamp("Begin Local Search")
                print("Begin Local Search")

                if self.LocalSearchState == "RESTART":
                    self.LocalSearchState = "CONTINUE"
                    # wfr 20210629 local search algorithm
                    AllTryCount = 0
                    arrayReward = -1 * np.ones(self.NumGears)
                    arrayConstraint = -1 * np.ones(self.NumGears)
                    arrayIPS = -1 * np.ones(self.NumGears)
                    arrayEng = -1 * np.ones(self.NumGears)
                    arrayInst = -1 * np.ones(self.NumGears)
                    arrayTimeIPS = -1 * np.ones(self.NumGears)
                    
                    arrayGearSIMPLE = -1 * np.ones(self.NumGears)
                    arrayEnergySIMPLE = -1 * np.ones(self.NumGears)
                    arrayTimeSIMPLE = -1 * np.ones(self.NumGears)

                    # wfr 20210629 measure predicted opt gear
                    self.CurrentGear.value = self.PredictedOptGear.value
                    print("Set CurrentGear = {:d}".format(self.CurrentGear.value))
                    if isMeasureOverhead == False:
                        EPOptDrv.SetEnergyGear(self.CurrentGear.value)
                        time.sleep(4) # 延时 1s, 使频率生效且稳定

                    # if True or localStateStable == True:
                    AllTryCount += 1
                    if localStateStable == True:
                        print("WorkMode: 简测量 PredictedOptGear = {}".format(self.CurrentGear.value))
                        self.dictFeature, TSimple = self.MeasureFeature("SIMPLE", localStateStable, "relaxed")
                        if self.isRun == False:
                            return
                        arrayEnergySIMPLE[self.CurrentGear.value] = self.dictFeature["Energy"]
                        arrayTimeSIMPLE[self.CurrentGear.value] = self.dictFeature["Time"]
                    else:
                        print("WorkMode: 测量 IPS PredictedOptGear = {}".format(self.CurrentGear.value))
                        # self.dictFeature, TSimple = self.MeasureFeature("IPS", localStateStable, StrictMode = "normal")
                        self.dictFeature, TSimple = self.MeasureFeature("IPS", False, "external", TFull*PredictedTime[int(self.CurrentGear.value - tmpGearBegin)])
                        if self.isRun == False:
                            return
                        arrayIPS[self.CurrentGear.value] = self.dictFeature[strIPS]
                        arrayInst[self.CurrentGear.value] = self.dictFeature[strInst]
                        arrayEng[self.CurrentGear.value] = self.dictFeature["Energy"]
                        arrayTimeIPS[self.CurrentGear.value] = self.dictFeature["Time"]
                    if False == self.TestSMUtil():
                        continue
                    self.SaveTPrev(TSimple, self.CurrentGear.value)
                    print("dictFeature:")
                    print(self.dictFeature)

                    arrayReward[self.CurrentGear.value], arrayConstraint[self.CurrentGear.value] = GetReward(self.dictFeature, self.Obj, localStateStable, ConstraintDefault)

                    print("Optimization Object: {}".format(self.Obj))
                    print("WorkMode: PredictedOptGear = {}; Reward = {}; Constraint = {}".format(self.CurrentGear.value, arrayReward[self.CurrentGear.value], arrayConstraint[self.CurrentGear.value]))

                    if self.CurrentMemClk.value >= self.arrayMemClk[3]:
                        radius = int(0.10* self.NumGears)
                    else:
                        radius = int(0.15* self.NumGears)

                    if isMeasureOverhead == False:
                        tmpReward = arrayReward[self.CurrentGear.value] / RewardDefault
                        if False and 1.03 * tmpReward <= self.PredictedOptReward and arrayConstraint[self.CurrentGear.value] <= 0.90 * self.Threshold:
                            self.SearchedOptGear.value = self.CurrentGear.value
                            print("WorkMode: SearchedOptGear = {}; 不进行 Golden-Section Search".format(self.SearchedOptGear.value))
                            GearHighDone = True
                            GearLowDone = True
                        elif arrayConstraint[self.PredictedOptGear.value] < 0.8 * self.Threshold:
                            print("WorkMode: PredictedOptGear 充分满足性能约束, 作为上界")
                            GearHighDone = True
                            GearLowDone = False
                            BetterFactor = 0.85
                            GearHigh = self.PredictedOptGear.value
                        elif arrayConstraint[self.PredictedOptGear.value] > 1.2 * self.Threshold:
                            print("WorkMode: PredictedOptGear 很不满足性能约束, 作为下界")
                            GearHighDone = False
                            GearLowDone = True
                            BetterFactor = 0.85
                            GearHigh = self.PredictedOptGear.value
                            GearLow = self.PredictedOptGear.value
                        else:
                            GearHighDone = False
                            GearLowDone = False
                            BetterFactor = 0.85
                            GearHigh = self.PredictedOptGear.value
                        
                    elif isMeasureOverhead == True:
                        GearHighDone = True
                        GearLowDone = True
                        GearHigh = int(self.PredictedOptGear.value + radius)
                        GearLow = int(self.PredictedOptGear.value - radius)
                else:
                    if self.SearchedOptMemClk.value >= self.arrayMemClk[3]:
                        radius = int(0.10* self.NumGears)
                    elif self.PredictedOptMemClk.value >= self.arrayMemClk[3]:
                        radius = int(0.10* self.NumGears)
                    elif self.CurrentMemClk.value >= self.arrayMemClk[3]:
                        radius = int(0.10* self.NumGears)
                    else:
                        radius = int(0.15* self.NumGears)
                    GearHighDone = False
                    GearLowDone = False
                    BetterFactor = 0.85
                    GearHigh = self.PredictedOptGear.value

                # wfr 20210629 explore search range's upper bound
                i = int(0)
                while GearHighDone == False:
                    i += int(1)
                    if i == 1:
                        print("Begin Find Upper Bound")
                        
                    GearHigh = int(min((self.NumGears-1), (GearHigh + radius)))
                    self.CurrentGear.value = GearHigh
                    # print("Set CurrentGear = {:d}".format(self.CurrentGear.value))
                    if arrayReward[self.CurrentGear.value] < 0:
                        if isMeasureOverhead == False:
                            EPOptDrv.SetEnergyGear(self.CurrentGear.value)
                            time.sleep(4) # 延时 1s, 使频率生效且稳定
                        TPrev, TNextPreference = self.EsimateTRange(self.CurrentGear.value)
                        AllTryCount += 1
                        if localStateStable == True:
                            print("WorkMode: 简测量 GearHigh = {}".format(self.CurrentGear.value))
                            self.dictFeature, TSimple = self.MeasureFeature("SIMPLE", localStateStable, "relaxed", TPrev, TNextPreference)
                            if self.isRun == False:
                                return
                            arrayEnergySIMPLE[self.CurrentGear.value] = self.dictFeature["Energy"]
                            arrayTimeSIMPLE[self.CurrentGear.value] = self.dictFeature["Time"]
                        else:
                            print("WorkMode: 测量 IPS GearHigh = {}".format(self.CurrentGear.value))
                            self.dictFeature, TSimple = self.MeasureFeature("IPS", False, "external", TFull*PredictedTime[int(self.CurrentGear.value - tmpGearBegin)])
                            if self.isRun == False:
                                return
                            arrayIPS[self.CurrentGear.value] = self.dictFeature[strIPS]
                            arrayInst[self.CurrentGear.value] = self.dictFeature[strInst]
                            arrayEng[self.CurrentGear.value] = self.dictFeature["Energy"]
                            arrayTimeIPS[self.CurrentGear.value] = self.dictFeature["Time"]
                        if False == self.TestSMUtil():
                            break
                        self.SaveTPrev(TSimple, self.CurrentGear.value)
                        print("dictFeature:")
                        print(self.dictFeature)
                        arrayReward[self.CurrentGear.value], arrayConstraint[self.CurrentGear.value] = GetReward(self.dictFeature, self.Obj, localStateStable, ConstraintDefault)
                    print("Optimization Object: {}".format(self.Obj))
                    print("WorkMode: GearHigh = {}; Reward = {}; Constraint = {}".format(self.CurrentGear.value, arrayReward[self.CurrentGear.value], arrayConstraint[self.CurrentGear.value]))


                    if GearHigh >= self.NumGears-1 or False == IsBetter(arrayReward[self.CurrentGear.value], arrayReward[self.PredictedOptGear.value], arrayConstraint[self.CurrentGear.value], arrayConstraint[self.PredictedOptGear.value], self.Obj, self.Threshold):
                        print("WorkMode: 找到 GearHigh = {}".format(GearHigh))
                        GearHighDone = True
                        break
                    elif True == IsBetter(arrayReward[self.CurrentGear.value], BetterFactor * arrayReward[self.PredictedOptGear.value], arrayConstraint[self.CurrentGear.value], arrayConstraint[self.PredictedOptGear.value], self.Obj, self.Threshold):
                        GearLow = self.PredictedOptGear.value
                        GearLowDone = True
                        self.PredictedOptGear.value = self.CurrentGear.value
                        print("WorkMode: 更新 PredictedOptGear = {}".format(self.CurrentGear.value))
                        print("WorkMode: 找到 GearLow = {}".format(GearLow))
                        print("WorkMode: 更新 GearHigh = {}".format(GearHigh))
                    sys.stdout.flush()

                    # wfr 20211031 这里进行判断, 如果 优化目标是 Performance, 约束是 Energy, 
                    # 如果能耗节省达不到约束, 则停止探索
                    if self.Obj == "Performance" and arrayConstraint[GearHigh] < self.Threshold:
                        print("WorkMode: 能耗节省不满足约束, 停止找 GearHigh")
                        break
                    # end while

                if False == self.TestSMUtil():
                    continue

                # wfr 20210629 explore search range's lower bound
                if GearLowDone == False:
                    GearLow = self.PredictedOptGear.value
                i = int(0)
                while GearLowDone == False:
                    i += int(1)
                    GearLow = int(max(tmpGearBegin, (GearLow - radius)))
                    self.CurrentGear.value = GearLow
                    if arrayReward[self.CurrentGear.value] < 0:
                        if isMeasureOverhead == False:
                            EPOptDrv.SetEnergyGear(self.CurrentGear.value)
                            time.sleep(4) # 延时 1s, 使频率生效且稳定
                        TPrev, TNextPreference = self.EsimateTRange(self.CurrentGear.value)
                        AllTryCount += 1
                        if localStateStable == True:
                            print("WorkMode: 简测量 GearLow = {}".format(self.CurrentGear.value))
                            self.dictFeature, TSimple = self.MeasureFeature("SIMPLE", localStateStable, "relaxed", TPrev, TNextPreference)
                            if self.isRun == False:
                                return
                            arrayEnergySIMPLE[self.CurrentGear.value] = self.dictFeature["Energy"]
                            arrayTimeSIMPLE[self.CurrentGear.value] = self.dictFeature["Time"]
                        else:
                            print("WorkMode: 测量 IPS GearLow = {}".format(self.CurrentGear.value))
                            self.dictFeature, TSimple = self.MeasureFeature("IPS", False, "external", TFull*PredictedTime[int(self.CurrentGear.value - tmpGearBegin)])
                            if self.isRun == False:
                                return
                            arrayIPS[self.CurrentGear.value] = self.dictFeature[strIPS]
                            arrayInst[self.CurrentGear.value] = self.dictFeature[strInst]
                            arrayEng[self.CurrentGear.value] = self.dictFeature["Energy"]
                            arrayTimeIPS[self.CurrentGear.value] = self.dictFeature["Time"]
                        if False == self.TestSMUtil():
                            break
                        self.SaveTPrev(TSimple, self.CurrentGear.value)
                        print("dictFeature:")
                        print(self.dictFeature)
                        arrayReward[self.CurrentGear.value], arrayConstraint[self.CurrentGear.value] = GetReward(self.dictFeature, self.Obj, localStateStable, ConstraintDefault)
                    print("Optimization Object: {}".format(self.Obj))
                    print("WorkMode: GearLow = {}; Reward = {}; Constraint = {}".format(self.CurrentGear.value, arrayReward[self.CurrentGear.value], arrayConstraint[self.CurrentGear.value]))


                    if GearLow <= tmpGearBegin or False == IsBetter(arrayReward[self.CurrentGear.value], arrayReward[self.PredictedOptGear.value], arrayConstraint[self.CurrentGear.value], arrayConstraint[self.PredictedOptGear.value], self.Obj, self.Threshold):
                        print("WorkMode: 找到 GearLow = {}".format(GearLow))
                        GearLowDone = True
                        break
                    elif True == IsBetter(arrayReward[self.CurrentGear.value], BetterFactor * arrayReward[self.PredictedOptGear.value], arrayConstraint[self.CurrentGear.value], arrayConstraint[self.PredictedOptGear.value], self.Obj, self.Threshold):
                        GearHigh = self.PredictedOptGear.value
                        GearHighDone = True
                        self.PredictedOptGear.value = self.CurrentGear.value
                        print("WorkMode: 更新 PredictedOptGear = {}".format(self.CurrentGear.value))
                        print("WorkMode: 更新 GearLow = {}".format(GearLow))
                        print("WorkMode: 找到 GearHigh = {}".format(GearHigh))
                    sys.stdout.flush()

                    # wfr 20211031 这里进行判断, 如果 优化目标是 Energy, 约束是 Performance, 
                    # 如果性能开销超过约束, 则停止探索
                    if self.Obj == "Energy" and arrayConstraint[GearLow] > self.Threshold:
                        print("WorkMode: 性能损失超过约束, 停止找 GearLow")
                        break

                    if arrayReward[self.CurrentGear.value ] / RewardDefault < 0.75:
                        print("WorkMode: Reward/RewardDefault < 0.75, 停止找 GearLow")
                        break
                # end
                
                if False == self.TestSMUtil():
                    continue

                # wfr 20210629 Golden-Section search
                print("Begin Golden-Section Search")
                Ratio = (1 + np.sqrt(5)) / 2 # golden ratio
                # init GearMiddle
                if GearHigh - self.PredictedOptGear.value > self.PredictedOptGear.value - GearLow:
                    GearMiddle = np.round(GearLow + Ratio / (1 + Ratio) * (GearHigh - GearLow)).astype(int)
                else:
                    GearMiddle = np.round(GearLow + 1 / (1 + Ratio) * (GearHigh - GearLow)).astype(int)
                
                # measure reward under GearMiddle
                self.CurrentGear.value = GearMiddle
                if arrayReward[self.CurrentGear.value] < 0 and self.SearchedOptGear.value < 0:
                    if isMeasureOverhead == False:
                        EPOptDrv.SetEnergyGear(self.CurrentGear.value)
                        time.sleep(4) # 延时 1s, 使频率生效且稳定
                    TPrev, TNextPreference = self.EsimateTRange(self.CurrentGear.value)
                    AllTryCount += 1
                    if localStateStable == True:
                        print("WorkMode: 简测量 GearMiddle = {}".format(self.CurrentGear.value))
                        self.dictFeature, TSimple = self.MeasureFeature("SIMPLE", localStateStable, "relaxed", TPrev, TNextPreference)
                        if self.isRun == False:
                            return
                        arrayEnergySIMPLE[self.CurrentGear.value] = self.dictFeature["Energy"]
                        arrayTimeSIMPLE[self.CurrentGear.value] = self.dictFeature["Time"]
                    else:
                        print("WorkMode: 测量 IPS GearMiddle = {}".format(self.CurrentGear.value))
                        # self.dictFeature, TSimple = self.MeasureFeature("IPS", localStateStable, "normal", TPrev, TNextPreference)
                        self.dictFeature, TSimple = self.MeasureFeature("IPS", False, "external", TFull*PredictedTime[int(self.CurrentGear.value - tmpGearBegin)])
                        if self.isRun == False:
                            return
                        arrayIPS[self.CurrentGear.value] = self.dictFeature[strIPS]
                        arrayInst[self.CurrentGear.value] = self.dictFeature[strInst]
                        arrayEng[self.CurrentGear.value] = self.dictFeature["Energy"]
                        arrayTimeIPS[self.CurrentGear.value] = self.dictFeature["Time"]
                    if False == self.TestSMUtil():
                        continue
                    self.SaveTPrev(TSimple, self.CurrentGear.value)
                    print("dictFeature:")
                    print(self.dictFeature)                 
                    
                    arrayReward[self.CurrentGear.value], arrayConstraint[self.CurrentGear.value] = GetReward(self.dictFeature, self.Obj, localStateStable, ConstraintDefault)
                    print("Optimization Object: {}".format(self.Obj))
                    print("WorkMode: GearMiddle = {}; Reward = {}; Constraint = {}".format(self.CurrentGear.value, arrayReward[self.CurrentGear.value], arrayConstraint[self.CurrentGear.value]))


                TryCount = 0
                while GearHigh - GearLow >= 7 and TryCount <= 5 and self.SearchedOptGear.value < 0:
                    if GearHigh - GearMiddle > GearMiddle - GearLow:
                        GearTry = np.round(GearMiddle + 1 / (1 + Ratio) * (GearHigh - GearMiddle)).astype(int)
                    else:
                        GearTry = np.round(GearMiddle - 1 / (1 + Ratio) * (GearMiddle - GearLow)).astype(int)

                    # measure reward under GearTry
                    self.CurrentGear.value = GearTry
                    if arrayReward[self.CurrentGear.value] < 0:
                        if isMeasureOverhead == False:
                            EPOptDrv.SetEnergyGear(self.CurrentGear.value)
                            time.sleep(4) # 延时 1s, 使频率生效且稳定
                        TPrev, TNextPreference = self.EsimateTRange(self.CurrentGear.value)
                        AllTryCount += 1
                        if localStateStable == True:
                            print("WorkMode: 简测量 GearTry = {}".format(self.CurrentGear.value))
                            self.dictFeature, TSimple = self.MeasureFeature("SIMPLE", localStateStable, "relaxed", TPrev, TNextPreference)
                            if self.isRun == False:
                                return
                            arrayEnergySIMPLE[self.CurrentGear.value] = self.dictFeature["Energy"]
                            arrayTimeSIMPLE[self.CurrentGear.value] = self.dictFeature["Time"]
                        else:
                            print("WorkMode: 测量 IPS GearTry = {}".format(self.CurrentGear.value))
                            self.dictFeature, TSimple = self.MeasureFeature("IPS", False, "external", TFull*PredictedTime[int(self.CurrentGear.value - tmpGearBegin)])
                            if self.isRun == False:
                                return
                            arrayIPS[self.CurrentGear.value] = self.dictFeature[strIPS]
                            arrayInst[self.CurrentGear.value] = self.dictFeature[strInst]
                            arrayEng[self.CurrentGear.value] = self.dictFeature["Energy"]
                            arrayTimeIPS[self.CurrentGear.value] = self.dictFeature["Time"]
                        if False == self.TestSMUtil():
                            break
                        self.SaveTPrev(TSimple, self.CurrentGear.value)
                        TryCount += 1
                        print("dictFeature:")
                        print(self.dictFeature)
                        
                        arrayReward[self.CurrentGear.value], arrayConstraint[self.CurrentGear.value] = GetReward(self.dictFeature, self.Obj, localStateStable, ConstraintDefault)
                        print("Optimization Object: {}".format(self.Obj))
                        print("WorkMode: GearTry = {}; Reward = {}; Constraint = {}".format(self.CurrentGear.value, arrayReward[self.CurrentGear.value], arrayConstraint[self.CurrentGear.value]))

                    if True == IsBetter(arrayReward[GearTry], arrayReward[GearMiddle], arrayConstraint[GearTry], arrayConstraint[GearMiddle], self.Obj, self.Threshold):
                        if GearMiddle < GearTry:
                            GearLow = GearMiddle
                        else:
                            GearHigh = GearMiddle
                        GearMiddle = GearTry
                    else:
                        if GearMiddle < GearTry:
                            GearHigh = GearTry
                        else:
                            GearLow = GearTry

                    print("WorkMode: GearLow = {}".format(GearLow))
                    print("WorkMode: GearMiddle = {}".format(GearMiddle))
                    print("WorkMode: GearTry = {}".format(GearTry))
                    print("WorkMode: GearHigh = {}".format(GearHigh))

                    try:
                        self.isRun = QueueGlobal.get(block = False)
                    except:
                        pass
                    if self.isRun == False:
                        print("Manager Process: isRun = {}".format(self.isRun))
                        return
                print("End Golden-Section Search")
                if False == self.TestSMUtil():
                    continue

                if self.SearchedOptGear.value < 0:
                    # wfr 20210629 select optimal gear according to measured data
                    # wfr 20211030 这里平滑数据, 重新计算 reward
                    if localStateStable == True:
                        tmpEnergySIMPLE = arrayEnergySIMPLE[arrayEnergySIMPLE>0]
                        tmpTimeSIMPLE = arrayTimeSIMPLE[arrayEnergySIMPLE>0]
                        arrayAllGear = np.arange(self.NumGears).astype(int)
                        tmpArrayGear = arrayAllGear[arrayEnergySIMPLE>0]
                        RewardMeaured = arrayReward[arrayEnergySIMPLE>0]

                        f_Energy = np.poly1d(np.polyfit(tmpArrayGear, tmpEnergySIMPLE, 3))
                        f_Time = np.poly1d(np.polyfit(tmpArrayGear, tmpTimeSIMPLE, 3))

                        tmpArrayGear = np.arange(np.max([16, np.min(tmpArrayGear)]), np.max(tmpArrayGear)+1, 1)
                        EnergySmooth = f_Energy(tmpArrayGear)
                        TimeSmooth = f_Time(tmpArrayGear)

                        print("EnergySmooth = {}".format(EnergySmooth))
                        print("TimeSmooth = {}".format(TimeSmooth))
                        print("ConstraintDefault = {}".format(ConstraintDefault))

                        RewardSmooth, ConstraintSmooth = GetArrayReward(EnergySmooth, TimeSmooth, self.Obj, ConstraintDefault)
                        print("RewardMeaured = {}".format(RewardMeaured))
                        print("RewardSmooth = {}".format(RewardSmooth))
                        print("ConstraintSmooth = {}".format(ConstraintSmooth))
                    else:
                        tmpEnergyIPS = arrayEng[arrayEng>0]
                        tmpTimeIPS = arrayTimeIPS[arrayEng>0]
                        arrayAllGear = np.arange(self.NumGears).astype(int)
                        tmpIPS = arrayIPS[arrayEng>0]
                        tmpInst = arrayInst[arrayEng>0]
                        tmpArrayGear = arrayAllGear[arrayEng>0]
                        RewardMeaured = arrayReward[arrayEng>0]

                        f_Energy = np.poly1d(np.polyfit(tmpArrayGear, tmpEnergyIPS, 3))
                        f_Time = np.poly1d(np.polyfit(tmpArrayGear, tmpTimeIPS, 3))
                        f_IPS = np.poly1d(np.polyfit(tmpArrayGear, tmpIPS, 3))
                        f_Inst = np.poly1d(np.polyfit(tmpArrayGear, tmpInst, 3))

                        tmpArrayGear = np.arange(np.max([16, np.min(tmpArrayGear)]), np.max(tmpArrayGear)+1, 1)
                        EnergySmooth = f_Energy(tmpArrayGear)
                        TimeSmooth = f_Time(tmpArrayGear)
                        IPSSmooth = f_IPS(tmpArrayGear)
                        InstSmooth = f_Inst(tmpArrayGear)

                        print("EnergySmooth = {}".format(EnergySmooth))
                        print("TimeSmooth = {}".format(TimeSmooth))
                        print("IPSSmooth = {}".format(IPSSmooth))
                        print("InstSmooth = {}".format(InstSmooth))
                        print("ConstraintDefault = {}".format(ConstraintDefault))

                        RewardSmooth, ConstraintSmooth = GetArrayRewardIPS(EnergySmooth, TimeSmooth, IPSSmooth, InstSmooth, self.Obj, ConstraintDefault)

                        # wfr 20211111 这里尝试进行一些修正, 保证默认约束, 即默认情况执行时间是最短的
                        if self.Obj == "Energy":
                            ConstraintDefault = min(ConstraintDefault, np.min(ConstraintSmooth))

                        print("RewardMeaured = {}".format(RewardMeaured))
                        print("RewardSmooth = {}".format(RewardSmooth))
                        print("ConstraintSmooth = {}".format(ConstraintSmooth))
                        # arrayConstraint[arrayEng>0] = ConstraintSmooth

                    self.SearchedOptGear.value = SelectOptGear(tmpArrayGear, RewardSmooth, ConstraintSmooth, self.Obj, self.Threshold)
                    self.CurrentGear.value = self.SearchedOptGear.value
                
                    if isMeasureOverhead == False:
                        EPOptDrv.SetEnergyGear(self.CurrentGear.value)
                        time.sleep(4) # 延时 1s, 使频率生效且稳定
                    print("Local Search Try Count: {}".format(AllTryCount))
                    print("Optimization Object: {}".format(self.Obj))
                    for i in range(len(tmpArrayGear)):
                        print("Gear = {}; RewardSmooth = {:.2f}".format(tmpArrayGear[i], RewardSmooth[i]))

                    print("WorkMode: Searched OptGear = {}; Reward = {}; Constraint = {}".format(self.CurrentGear.value, arrayReward[self.CurrentGear.value], arrayConstraint[self.CurrentGear.value]))
                    if self.Obj == "Energy":
                        tmpConstraint = arrayConstraint[self.CurrentGear.value]
                        print("ConstraintMeasured = {}; Constraint = {}".format(tmpConstraint, self.Threshold))
                    elif self.Obj == "Performance":
                        tmpConstraint = arrayConstraint[self.CurrentGear.value]
                        print("ConstraintMeasured = {}; Constraint = {}".format(tmpConstraint, self.Threshold))
                    print("End Local Search")

            if isMeasureOverhead == True:
                self.SearchedOptGear.value = self.BaseGear
            else:
                # wfr 20211110 如果有较长时间没有使用 GPU, 则不再进行常规的优化过程
                # 而是使用指定的 频率配置
                if self.SMUsedDuraiton.value > 6 and self.SMUnusedDuraiton.value > 6 and self.SMUnusedDuraiton.value / self.SMUsedDuraiton.value > 0.2:
                    time.sleep(1)
                    EPOptDrv.ResetMemClkRange()
                    time.sleep(1)
                    EPOptDrv.ResetEnergyGear()

            TimeStamp("Begin MeasureUntilUnstable")
            print("Begin MeasureUntilUnstable")

            # 进行简测量, 直到系统不稳定
            print("WorkMode: 简测量直到不稳定")
            self.isStateStable = self.MeasureUntilUnstable("SIMPLE", 1.5 * TFull)

            # 检查是否停止运行
            if self.isRun == False:
                return
            try:
                self.isRun = QueueGlobal.get(block = False)
            except:
                pass
            if self.isRun == False:
                print("Manager Process: isRun = {}".format(self.isRun))
                return


    def LearnWork(self):
        return

    def run(self):
        print("run: Manager Process")

        #进程ID
        PID = os.getpid()
        print("PyEPOpt.run(): PID = {:x}".format(PID))
        # 1 获取线程ID,NAME
        tmpThread = threading.currentThread()
        #线程ID
        print("PyEPOpt.run(): TID = {:x}".format(tmpThread.ident))

        # 初始化
        self.Init()

        self.MyManager = multiprocessing.Manager()
        self.SMUtilTolerateFlag = self.MyManager.Value(bool, True)
        self.SMUtil0_TolerateDuration = self.MyManager.Value(float, 2.0)
        self.SMUsedDuraiton = self.MyManager.Value(float, -1.0)
        self.SMUnusedDuraiton = self.MyManager.Value(float, -1.0)

        self.SearchedOptGear = self.MyManager.Value(int, -1)
        self.PredictedOptGear = self.MyManager.Value(int, -1)
        self.CurrentGear = self.MyManager.Value(int, -1)
        
        self.SearchedOptMemClk = self.MyManager.Value(int, -1)
        self.PredictedOptMemClk = self.MyManager.Value(int, -1)
        self.CurrentMemClk = self.MyManager.Value(int, -1)

        ProcessWatch = Process(target=WatchSMUsed0, args=(self.SMUtilTolerateFlag, self.SMUtil0_TolerateDuration, self.SMUsedDuraiton, self.SMUnusedDuraiton, self.SearchedOptGear, self.PredictedOptGear, self.CurrentGear, self.SearchedOptMemClk, self.PredictedOptMemClk, self.CurrentMemClk))
        ProcessWatch.start()

        # time.sleep(3) # 延时, 等待程序稳定

        # print("Manager Process: isRun = {}".format(self.isRun))
        print("PyEPOpt.run(): self.RunMode = {}".format(self.RunMode))

        if self.RunMode == self.RUN_MODE["LEARN"]:
            self.LearnMode()
        elif self.RunMode == self.RUN_MODE["WORK"]:
            self.WorkMode()
        elif self.RunMode == self.RUN_MODE["LEARN_WORK"]:
            self.LearnWork()

        EPOptDrv.ManagerStop()
        try:
            ProcessWatch.join()
        except:
            pass
        try:
            ProcessWatch.terminate()
        except:
            pass
        del self.MyManager
        print("Manager Process: End")

    def Begin(self, inDeviceIDCUDADrv, inDeviceIDNVML, inRunMode="LEARN", inMeasureOutDir="NONE", inModelDir="", inTestPrefix=""):

        # RunMode = "WORk" / "LEARN" / "MEASURE"
        # 这里需要锁
        # self.lockIsRun.acquire()
        if self.isRun == True:
            # self.lockIsRun.release()
            return # 防止重复启动
        else:
            self.isRun = True
            # self.lockIsRun.release()

        
        #进程ID
        PID = os.getpid()
        print("PyEPOpt.Begin(): PID = {:x}".format(PID))
        # 1 获取线程ID,NAME
        tmpThread = threading.currentThread()
        #线程ID
        print("PyEPOpt.Begin(): TID = {:x}".format(tmpThread.ident))
        

        self.DeviceIDCUDADrv = inDeviceIDCUDADrv
        self.DeviceIDNVML = inDeviceIDNVML
        self.MeasureOutDir = inMeasureOutDir
        self.ModelDir = inModelDir
        self.TestPrefix = inTestPrefix

        # 确定运行模式和测量模式
        self.RunMode = self.RUN_MODE[inRunMode]
        print("PyEPOpt.Begin(): inRunMode = {}".format(inRunMode))
        print("PyEPOpt.Begin(): self.RunMode = {}".format(self.RunMode))
        if self.RunMode == self.RUN_MODE["WORK"] or self.RunMode == self.RUN_MODE["LEARN"] or self.RunMode == self.RUN_MODE["LEARN_WORK"]:
            # 这里需要完成的工作
            # 1. 初始化并启动测量线程（C++）
            # 2. 初始化并启动频率调节进程的主线程（python）
            # 3. 初始化并启动频率调节进程的子线程（C++）（这个要在频率调节主线程中完成）

            self.listMetricGroup, self.listMetricIPS = SetMetric(False, self.GPUName)
            self.listFeatureName = ["Energy", "Time", "Power", "SMUtil", "MemUtil"] + list(chain(*self.listMetricGroup))
            tmplist = [0.0] * len(self.listFeatureName)
            self.dictFeature = dict(zip(self.listFeatureName, tmplist))

            # 启动新进程
            print("before self.start()")
            self.start()
            print("after self.start()")
            time.sleep(3) # 延时 1s

            # 1. 初始化并启动测量线程（C++）
            self.isInit = EPOptDrv.MeasurerInit(self.DeviceIDCUDADrv, self.DeviceIDNVML, self.RunMode, self.MEASURE_STOP_MODE["SIGNAL"], self.listMetricGroup[0], self.MeasureDurationInit, self.isMeasurePower, self.isMeasurePerformace)

            # if self.isInit < 0:
            #     return

            # # 启动新进程
            # self.start()
        elif self.RunMode == self.RUN_MODE["MEASURE"]:
            self.DeviceIDCUDADrv = inDeviceIDCUDADrv
            self.DeviceIDNVML = inDeviceIDNVML
            self.MeasureOutDir = inMeasureOutDir

            self.listMetricGroup, self.listMetricIPS = SetMetric(True, self.GPUName)
            self.listFeatureName = ["Energy", "Time", "Power", "SMUtil", "MemUtil"] + list(chain(*self.listMetricGroup))
            tmplist = [0.0] * len(self.listFeatureName)
            self.dictFeature = dict(zip(self.listFeatureName, tmplist))

            self.isInit = EPOptDrv.MeasurerInitInCode(self.DeviceIDCUDADrv, self.DeviceIDNVML, self.RunMode, self.listMetricGroup[0], self.isMeasurePower, self.isMeasurePerformace)

    def End(self):

        global QueueGlobal, QueueGlobalWatch

        #进程ID
        PID = os.getpid()
        print("PyEPOpt.End(): PID = {:x}".format(PID))
        # 1 获取线程ID,NAME
        tmpThread = threading.currentThread()
        #线程ID
        print("PyEPOpt.End(): TID = {:x}".format(tmpThread.ident))

        if self.RunMode == self.RUN_MODE["WORK"] or self.RunMode == self.RUN_MODE["LEARN"] or self.RunMode == self.RUN_MODE["LEARN_WORK"]:
            # 这里需要锁
            # start = time.time()
            # self.lockIsRun.acquire()
            # print("End wait lock: {0}s".format(time.time()-start))
            if self.isRun == False:
                # self.lockIsRun.release()
                return # 没启动则直接退出
            else:
                self.isRun = False
                print("self.isRun = False")
                try:
                    QueueGlobal.put(False, block = False)
                    print("QueueGlobal.put(False, block = False)")
                    QueueGlobalWatch.put(False, block = False)
                    print("QueueGlobalWatch.put(False, block = False)")
                    sys.stdout.flush()
                except:
                    pass
                # self.lockIsRun.release()

            EPOptDrv.MeasurerSendStopSignal2Manager()

            start = time.time()
            try:
                self.join() # 等待频率调节进程结束, 0 表示不等待立即结束子进程
            except:
                pass
            try:
                self.terminate()
            except:
                pass
            print("End wait join: {0}s".format(time.time()-start))
            sys.stdout.flush()

            # start = time.time()
            EPOptDrv.MeasurerStop()
            # print("End wait MeasurerStop: {0}s".format(time.time()-start))

            print("Measurer Thread: End")
            sys.stdout.flush()
        elif self.RunMode == self.RUN_MODE["MEASURE"]:

            # 将测量结果存入字典
            self.dictFeature = EPOptDrv.MeasurerEndInCode()
            print("PyEPOpt.End(): len(self.dictFeature) = {}".format(len(self.dictFeature)))

            print("dictFeature:")
            print(self.dictFeature)

            # wfr 20210508 从数据文件中读取所有数据
            MetricData = ""
            if os.path.exists(self.MeasureOutDir):
                with open(self.MeasureOutDir, "r") as MetricFile:
                    MetricData = MetricFile.read()

            # wfr 20210508 先搜索现有数据中是否有 当前 key, 如果有就 修改 value, 没有 添加 "key: value\n"
            for key,value in self.dictFeature.items():
                tmpStr = key + ": "
                pos0 = MetricData.find(tmpStr)
                if pos0 >= 0:
                    pos1 = MetricData.find("\n", pos0+len(tmpStr))
                    if pos1 == -1:
                        pos1 = len(MetricData)
                    MetricData = MetricData[:(pos0+len(tmpStr))] + str(value) + MetricData[pos1:]
                else:
                    MetricData += key + ": " + str(value) + "\n"

            # wfr 20210508 写入更新后的数据到文件
            with open(self.MeasureOutDir, "w") as MetricFile:
                MetricFile.write(MetricData)

        
EPOpt = EP_OPT()

