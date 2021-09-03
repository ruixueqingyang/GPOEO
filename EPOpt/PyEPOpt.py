# -*- coding: utf-8 -*-
import math
import numpy as np                # 导入模块 numpy，并简写成 np
import matplotlib.pyplot as plt   # 导入模块 matplotlib.pyplot，并简写成 plt 
import os
import threading
import pickle
import time
import multiprocessing
from multiprocessing import Process, Lock, Manager, Value
import sys
from collections import deque
from itertools import chain

# lsc writes here~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
FLAG = True # set False if want to measure overhead

import sys
import os
tmpDir = os.path.abspath(__file__)
tmpDir = os.path.split(tmpDir)[0]
tmpDir = os.path.abspath(tmpDir)
sys.path.append(tmpDir)
tmpDir = os.path.abspath(tmpDir,"build")
sys.path.append(tmpDir)

import EPOptDrv
from Msg2EPRT import TimeStamp
from StateReward import SetMetric, SelectOptGear, IsBetter, GetReward, GetArrayReward
from SpectrumAnalysis import T_SpectrumAnalysis

QueueGlobal = multiprocessing.Queue()
QueueGlobalWatch = multiprocessing.Queue()

MyManager = multiprocessing.Manager()
SMUtilTolerateFlag = MyManager.Value(bool, True)
SMUtil0_TolerateDuration = MyManager.Value(float, 7.0)
SMUsedDuraiton = MyManager.Value(float, -1.0)
SMUnusedDuraiton = MyManager.Value(float, -1.0)
SearchedOptGear = MyManager.Value(int, -1)
PredictedOptGear = MyManager.Value(int, -1)
CurrentGear = MyManager.Value(int, -1)

# wfr 20210826 start a thread for this func to handle SMUtil == 0
def WatchSMUsed0():
    global QueueGlobalWatch
    global SMUtilTolerateFlag, SMUtil0_TolerateDuration, SMUsedDuraiton, SMUnusedDuraiton, SearchedOptGear, PredictedOptGear, CurrentGear

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
                    if FLAG:
                        EPOptDrv.SetEnergyGear(CurrentGear.value)
                    print("WatchSMUsed0: Set CurrentGear = {:d}".format(CurrentGear.value))
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
                    if SearchedOptGear.value > 0:
                        CurrentGear.value = SearchedOptGear.value
                        if FLAG:
                            EPOptDrv.SetEnergyGear(CurrentGear.value)
                        print("WatchSMUsed0: Reset CurrentGear = {:d}".format(CurrentGear.value))
                    elif PredictedOptGear.value > 0:
                        CurrentGear.value = PredictedOptGear.value
                        if FLAG:
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
    SMClkGearCount = int(109)
    # BaseGear = 70 # 1350 MHz(70); 1545 MHz(83)
    BaseGear = int(77) # 1365 MHz(77)
    MinSMClk = int(210)
    MaxSMClk = int(1830)
    BaseSMClk = int(1365)
    SMClkStep = int(15)
    # CurrentGear = int(-1)
    GPUName = "RTX3080Ti"
    # TUpper = 1e9
    # TLower = 0
    TPrev = -1
    TNextPreference = int(0)
    SMClkPrev = int(1000)
    SMUtil = int(100)
    # SMUtil0_TolerateDuration = 7
    # SMUtilTolerateFlag = True
    SMUsedBeginTimeStamp = -1.0
    SMUnusedCount = int(0)
    # SMUsedDuraiton = -1.0
    # SMUnusedDuraiton = -1.0
    SMUnusedRatioThreshold = 0.1
    # PredictedOptGear = int(-1)
    # SearchedOptGear = int(-1)
    TimeIncFactor = 1.05
    TimeDecFactor = 0.98
    IPSIncFactor = 1.02
    EngDecFactor = 0.95
    MeasureDurationInit = 40

    def __init__(self):
        multiprocessing.Process.__init__(self)
        global SMUtilTolerateFlag, SMUtil0_TolerateDuration, SMUsedDuraiton, SMUnusedDuraiton, SearchedOptGear, PredictedOptGear, CurrentGear

        self.isMeasureOverHead = False # wfr 20210504 measure cupti overhead

        self.isMeasurePower = True
        self.isMeasurePerformace = True
        self.MeasureDuration = 4 # 4
        self.SampleInterval = 100 # 采样周期 单位是 ms
        self.isRun = False
        self.lockIsRun = multiprocessing.Lock()
        self.DeviceIDCUDADrv = -1
        self.DeviceIDNVML = -1
        self.RUN_MODE = {'WORK': int(0), 'LEARN': int(1), 'LEARN_WORK': int(2), 'MEASURE': int(3)}
        self.RunMode = 0
        self.MEASURE_STOP_MODE = {"TIMER": int(0), "SIGNAL": int(1)}
        # self.MEASURE_BEGIN_SIGNAL = {"SIMPLE": int(0), "FULL": int(1)}
        self.MeasureMode = 1
        self.MeasureOutDir = "NONE"
        # self.QTableDir = "/home/wfr/work/Energy/EPOpt/QTable"
        self.QTableDir = "/home/wfr/work/Energy/EPOpt/DataAnalysis"
        self.TestPrefix = ""
        
        # self.listMetricGroup, self.listMetricIPS = SetMetric()
        # self.listFeatureName = ["Energy", "Time"] + list(chain(*self.listMetricGroup))
        # tmplist = [0.0] * len(self.listFeatureName)
        # self.dictFeature = dict(zip(self.listFeatureName, tmplist))

        self.listTrace = [0, 0]
        self.Obj = "ED2P"
        self.PerfLoss = 0.10 # require performace loss within 10%
        self.EngSave = 0.10 # require energy saving over 10%
        self.Threshold = -1.0

        self.NumGears = self.SMClkGearCount

        self.TFixedDefault = 8
        self.TFixed = self.TFixedDefault
        self.TUpBound = 35 # 考虑的最大周期
        self.TUpBoundNew = self.TUpBound # 考虑的最大周期
        
        self.FileCount = 0

        # 初始化开始测量信号，初始化为全测量，即测量性能计数器
        self.FullCount = 0
        self.SimpleCount = 0
        # self.MeasureBeginSignal = self.MEASURE_BEGIN_SIGNAL["FULL"]
        self.NumPower = 3 # 三次测量的能耗相差不大才进入 简测量 模式
        self.NumT = 3 # 三次测量的周期相差不大才进入 简测量 模式
        self.dequePower = deque([]) # 初始化功率队列
        # self.dequeT = deque([]) # 初始化周期队列
        self.StateOld = np.zeros(3)
        self.StateNew = np.zeros(3)
        self.StateFull = np.zeros(3)
        self.StateSimple = np.zeros(3)
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
        global SMUtilTolerateFlag, SMUtil0_TolerateDuration, SMUsedDuraiton, SMUnusedDuraiton, SearchedOptGear, PredictedOptGear, CurrentGear
        if self.SMUnusedCount>=3 and SMUnusedDuraiton.value / SMUsedDuraiton.value > self.SMUnusedRatioThreshold:
            return True
        else:
            return False

    # wfr 20210825 is SMUtil == 0 stably or not
    def TestSMUtil(self):
        global SMUtilTolerateFlag, SMUtil0_TolerateDuration, SMUsedDuraiton, SMUnusedDuraiton, SearchedOptGear, PredictedOptGear, CurrentGear
        return SMUtilTolerateFlag.value

    # wfr 20210824 when SMUtil == 0%, enter this func, until SMUtil > 0%, then return from this func
    def MeasureUntilSMUsed(self):
        global SMUtilTolerateFlag, SMUtil0_TolerateDuration, SMUsedDuraiton, SMUnusedDuraiton, SearchedOptGear, PredictedOptGear, CurrentGear
        print("MeasureUntilSMUsed: Begin")
        tmpTimeStamp = time.time()

        tmpSMClk = int(EPOptDrv.GetCurrSMClk())
        print("MeasureUntilSMUsed: GetCurrSMClk = {}".format(tmpSMClk))

        if SMUtilTolerateFlag.value == False and tmpSMClk != self.MinSMClk:
            CurrentGear.value = int(0*self.NumGears)
            if FLAG:
                EPOptDrv.SetEnergyGear(CurrentGear.value)
            print("MeasureUntilSMUsed: Set CurrentGear = {:d}".format(CurrentGear.value))
            sys.stdout.flush()

        # self.SMUtil = int(0)
        while SMUtilTolerateFlag.value == False:

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


    # wfr 20201222 测量直到认为是稳定状态
    def MeasureUntilStable(self, MeasureStateMode, StrictMode = "normal", TPrev = -1, TNextPreference = int(0)):
        global QueueGlobal
        global SMUtilTolerateFlag, SMUtil0_TolerateDuration, SMUsedDuraiton, SMUnusedDuraiton, SearchedOptGear, PredictedOptGear, CurrentGear

        FlagFULL_SIMPLE = True
        FlagIPS_SIMPLE = True

        ZeroTime = 0
        ZeroTimeThreshold = 5

        print("MeasureUntilStable: MeasureStateMode = {}".format(MeasureStateMode))

        if MeasureStateMode == "FULL" or MeasureStateMode == "IPS":
            if self.isMeasureOverHead == True: # wfr 20210504 measure cupti overhead
                # EPOptDrv.SetEnergyGear(self.NumGears)
                print("MeasureFeature: do not set gear")
            else:
                # 重置频率为 1350MHz
                if FLAG:
                    EPOptDrv.SetEnergyGear(self.BaseGear)
                # 重置频率调节策略为 驱动默认
                # EPOptDrv.ResetEnergyGear()
                time.sleep(1) # 延时 1s, 使频率生效且稳定

        if TPrev > 0:
            TEstimated = TPrev
        else:
            TEstimated = 8.0

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
            return (0.15 * SMUsedDuraiton.value), True


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

            # # 延时, 这里要减去中间数据处理的时间, 因为测量与数据处理并行, 有时间上的重叠
            # try:
            #     tmpDelay = MeasureDurationNext-(time.time()-PrevTimeStamp)
            #     print("MeasureUntilStable: 延时 {0:.2f} s".format(tmpDelay))
            #     self.isRun = QueueGlobal.get( timeout=(tmpDelay) ) # 延时，如果收到进程结束信号则立即结束延时
            # except:
            #     pass
            # if self.isRun == False:
            #     EPOptDrv.StopMeasure()
            #     print("MeasureUntilStable: isRun = {}, in sleep".format(self.isRun))
            #     return TEstimated, self.isStateStable
            
            print("MeasureUntilStable: 延时 complete")
            sys.stdout.flush()

            # 获得 trace
            EPOptDrv.ReceiveData() # 收数据
            PrevTimeStamp = time.time() # 记录时间戳
            self.listTrace = EPOptDrv.GetTrace() # 读取数据
            # SumMeasureDuration += MeasureDurationNext
            SumMeasureDuration = len(self.listTrace) * self.SampleInterval / 1000
            print("MeasureUntilStable: len of listTrace = {}".format(len(self.listTrace)))

            # 频谱分析判断是否稳定
            if len(self.listTrace) == 0:
                print("MeasureUntilStable WARNING: len of listTrace = 0")
                self.isStateStable = False
                ZeroTime += 1
                if ZeroTime >= ZeroTimeThreshold:
                    self.isRun = False
                    TEstimated = 8.1
                    return TEstimated, self.isStateStable
            else:
                TraceFileName = self.TestPrefix+"-PowerTarce-"+str(self.FileCount)
                print("Before T_SpectrumAnalysis: TPrev = {}; TNextPreference = {}".format(TPrev, TNextPreference))
                TEstimated, self.isStateStable, MeasureDurationNext = T_SpectrumAnalysis(self.listTrace, self.SampleInterval, self.TUpBoundNew, MeasureTFactor, TraceFileName, StrictMode, TPrev, TNextPreference)
                listTEstimated.append(TEstimated)
                listMeasureDurationNext.append(MeasureDurationNext)

                if len(listTEstimated) >= 2:
                    print("listTEstimated = {}".format(listTEstimated))
                    print("listMeasureDurationNext = {}".format(listMeasureDurationNext))
                    # listMeasureDurationNext[-1]/listTEstimated[-1] > listMeasureDurationNext[-2]/listTEstimated[-2]
                    # TEstimated = min(listTEstimated)
                    # break
        
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
        global SMUtilTolerateFlag, SMUtil0_TolerateDuration, SMUsedDuraiton, SMUnusedDuraiton, SearchedOptGear, PredictedOptGear, CurrentGear

        if True == self.isStateStable:
            PowerError = 0.18
        else:
            PowerError = 0.3

        ReFullMeasureThreshold = 0.5

        MeasureStateMode = "SIMPLE"
        self.SimpleCount = 0
        # self.dequeT.clear()
        self.dequePower.clear()

        print("MeasureUntilUnstable: isStateStable = {0}".format(self.isStateStable))
        if self.isStateStable == False:
            TEstimated = self.TFixed
            time.sleep(1)
        elif self.isStateStable == True:
            TEstimated, self.isStateStable = self.MeasureUntilStable(MeasureStateMode, "normal", TRef)
            if self.isStateStable == False or self.isRun == False:
                return self.isStateStable

            tmpLenEnd = len(self.listTrace)
            tmpMeasureDuration = (tmpLenEnd - 1) * (self.SampleInterval / 1000)
            tmpMeasureCount = int(np.floor( tmpMeasureDuration / TEstimated ))
            tmpLenT = int( round( TEstimated / (self.SampleInterval/1000) ) ) # 取出最后的 TEstimated 时间内的 采样数据
            for i in range(tmpMeasureCount-1):
                tmpIndexBegin = tmpLenEnd - (i+1) * tmpLenT - 1
                tmpIndexEnd = tmpLenEnd - (i) * tmpLenT
                array0 = np.array(self.listTrace[tmpIndexBegin:tmpIndexEnd])
                PowerSimple = np.mean(array0) # 平均功率

                if len(self.dequePower) != 2:
                    self.dequePower.append(PowerSimple) # init min power
                    self.dequePower.append(PowerSimple) # init max power
                else:
                    if PowerSimple < self.dequePower[0]:
                        self.dequePower[0] = PowerSimple
                    elif PowerSimple > self.dequePower[1]:
                        self.dequePower[1] = PowerSimple

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

            # try:
            #     tmpDelay = TEstimated
            #     print("MeasureUntilUnstable: 延时 {0:.2f} s".format(tmpDelay))
            #     self.isRun = QueueGlobal.get( timeout=(tmpDelay+1.5) ) # 延时，如果收到进程结束信号则立即结束延时
            # except:
            #     pass
            # if self.isRun == False:
            #     EPOptDrv.StopMeasure()
            #     print("Manager Process: isRun = {}, in sleep".format(self.isRun))
            #     return self.isStateStable


            EPOptDrv.StopMeasure()
            print("MeasureUntilUnstable: EPOptDrv.GetTrace()")
            listTrace = EPOptDrv.GetTrace() # 读取数据
            print("MeasureUntilUnstable: len of listTrace = {}".format(len(self.listTrace)))
            sys.stdout.flush()
            
            tmpLenT = int( round( tmpDelay / (self.SampleInterval/1000) ) ) # 取出最后的 tmpDelay 时间内的采样点
            tmpLenEnd = len(listTrace)

            if tmpLenEnd >= tmpLenT:
                tmpIndexBegin = tmpLenEnd - tmpLenT - 1
                tmpIndexEnd = tmpLenEnd
                array0 = np.array(listTrace[tmpIndexBegin:tmpIndexEnd])
                PowerSimple = np.mean(array0) # 平均功率
            else:
                dictFeature = EPOptDrv.GetFeature() # 读取数据
                print("MeasureUntilUnstable: dictFeature:")
                print(dictFeature)
                PowerSimple = dictFeature["Energy"] / np.max([1e-9, dictFeature["Time"]])

            self.SimpleCount += 1
            sys.stdout.flush()
            
            # 如果是首次 简测量，就 清空队列 再 保存第一次的 PowerSimple 既为最小值也为最大值
            # dequePower[0] 保存最小值，dequePower[1] 保存最大值
            if len(self.dequePower) != 2:
                self.dequePower.clear()
                self.dequePower.append(PowerSimple)
                self.dequePower.append(PowerSimple)
            else:
                if PowerSimple < self.dequePower[0]:
                    self.dequePower[0] = PowerSimple
                elif PowerSimple > self.dequePower[1]:
                    self.dequePower[1] = PowerSimple
            minPower = min(self.dequePower)
            maxPower = max(self.dequePower)
            meanPower = sum(self.dequePower) / len(self.dequePower)

            # 偏差过大则认为应用运行进入不稳定状态
            if abs((maxPower-minPower)/meanPower) > PowerError:
                
                if True == self.IsSMUnusedPeriodly():
                    pass
                elif abs((maxPower-minPower)/meanPower) < ReFullMeasureThreshold:
                    PredictedOptGear.value = SearchedOptGear.value
                    SearchedOptGear.value = int(-1)
                else:
                    PredictedOptGear.value = int(-1)
                    SearchedOptGear.value = int(-1)

                self.dequePower.clear()
                self.SimpleCount = int(0)
                self.isStateStable = False
                print("MeasureUntilUnstable: dequePower: {}".format(self.dequePower))
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

                # try:
                #     tmpDelay = NumInterval * TEstimated
                #     print("MeasureUntilUnstable: 休眠 {0:.2f} s".format(tmpDelay))
                #     self.isRun = QueueGlobal.get( timeout=(tmpDelay) ) # 延时，如果收到进程结束信号则立即结束延时
                # except:
                #     pass
                # if self.isRun == False:
                #     print("Manager Process: isRun = {}, in sleep".format(self.isRun))
                #     return self.isStateStable
            sys.stdout.flush()
        self.isStateStable = False
        return self.isStateStable

    def MeasureFeature(self, MeasureStateMode, IsTryDetectPeriod=True, StrictMode = "normal", TPrev = -1, TNextPreference = int(0)):
        global QueueGlobal
        global SMUtilTolerateFlag, SMUtil0_TolerateDuration, SMUsedDuraiton, SMUnusedDuraiton, SearchedOptGear, PredictedOptGear, CurrentGear

        print("\nMeasureFeature: MeasureStateMode = {}".format(MeasureStateMode))

        dictFeature = {"Energy": 1e5, "Time": self.TUpBound}

        if MeasureStateMode == "FULL":
            if self.isMeasureOverHead == True: # wfr 20210504 measure cupti overhead
                print("MeasureFeature: do not set gear")
            else:
                # 重置频率为 1350 MHz
                if FLAG:
                    EPOptDrv.SetEnergyGear(self.BaseGear)
            time.sleep(1) # 延时 1s, 使频率生效且稳定
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
            return dictFeature, TEstimated

        sys.stdout.flush()

        if MeasureStateMode == "SIMPLE":
            if IsTryDetectPeriod == False:
                EPOptDrv.StartMeasure([], "SIMPLE_FEATURE_TRACE")
                tmpTimeStampStart = time.time()

                tmpDelay = 2 * TEstimated
                print("MeasureUntilStable: 延时 {0:.2f} s".format(tmpDelay))
                sys.stdout.flush()
                while tmpDelay > 0:
                    tmpTimeStamp = time.time()
                    if False == self.TestSMUtil():
                        time.sleep( max(0, 1-(time.time()-tmpTimeStampStart)) )
                        EPOptDrv.StopMeasure()
                        return dictFeature, TEstimated
                    # 延时, 这里要减去中间数据处理的时间, 因为测量与数据处理并行, 有时间上的重叠
                    try:
                        self.isRun = QueueGlobal.get( timeout=(0.2) ) # 延时，如果收到进程结束信号则立即结束延时
                    except:
                        pass
                    if self.isRun == False:
                        EPOptDrv.StopMeasure()
                        print("MeasureUntilStable: isRun = {}, in sleep".format(self.isRun))
                        return dictFeature, TEstimated

                    tmpDelay = tmpDelay - (time.time()-tmpTimeStamp)

                # try:
                #     tmpDelay = 2 * TEstimated
                #     print("延时 {0:.2f} s".format(tmpDelay))
                #     self.isRun = QueueGlobal.get( timeout=(tmpDelay+1.5) ) # 延时，如果收到进程结束信号则立即结束延时
                # except:
                #     pass
                # if self.isRun == False:
                #     EPOptDrv.StopMeasure()
                #     print("Manager Process: isRun = {}, in sleep".format(self.isRun))
                #     return dictFeature, TEstimated
                EPOptDrv.StopMeasure()
                print("MeasureFeature: EPOptDrv.GetTrace()")
                self.listTrace = EPOptDrv.GetTrace() # 读取数据
                print("MeasureFeature: len of listTrace = {}".format(len(self.listTrace)))
            sys.stdout.flush()
            # 从 self.listTrace 中取出最后一个 TEstimated 的数据计算特征
            dictFeature["Time"] = TEstimated
            tmpLenEnd = len(self.listTrace)
            tmpLenT = 2 * int( round( TEstimated / (self.SampleInterval/1000) ) ) # 取出最后的 2个 TEstimated 时间内的 采样数据
            tmpLenT = min(tmpLenT, (tmpLenEnd-2))
            array0 = np.array(self.listTrace[(tmpLenEnd-tmpLenT-1):tmpLenEnd])
            array1 = np.array(self.listTrace[(tmpLenEnd-tmpLenT-2):tmpLenEnd-1])
            dictFeature["Energy"] = np.mean(array0 + array1)/2 * TEstimated # 平均功率 * 时间 (用一阶线性插值减小误差)
        elif MeasureStateMode == "FULL":
            # 这里需要高精度测量, 所以在 C++级别 定时
            # wfr 20210213 使用 C++级别 定时 的劣势是: 定时过程中不能被 python 级别的信号打断, 即不能提前结束

            sumEnergy = 0.0
            sumTime = 0.0
            for i in range(len(self.listMetricGroup)):
                EPOptDrv.MeasureDuration(self.listMetricGroup[i], "FEATURE", TEstimated)
                tmpDictFeature = EPOptDrv.GetFeature() # 读取数据
                sumEnergy += tmpDictFeature["Energy"]
                sumTime += tmpDictFeature["Time"]
                del tmpDictFeature["Energy"]
                del tmpDictFeature["Time"]
                dictFeature.update(tmpDictFeature)
                # wfr 20210825 if SMUtil == 0, no more measurements
                if False == self.TestSMUtil():
                    break
            dictFeature["Energy"] = sumEnergy / len(self.listMetricGroup)
            dictFeature["Time"] = sumTime / len(self.listMetricGroup)

        elif MeasureStateMode == "IPS":

            # 重置频率为 1350 MHz
            # EPOptDrv.SetEnergyGear(self.BaseGear)
            # time.sleep(1) # 延时 1s, 使频率生效且稳定

            # wfr 20210825 if SMUtil != 0, then measure
            if True == self.TestSMUtil():
                EPOptDrv.MeasureDuration(self.listMetricIPS, "FEATURE", TEstimated)
                dictFeature = EPOptDrv.GetFeature() # 读取数据

            dictFeature["Energy"] = self.EngDecFactor * dictFeature["Energy"]
            dictFeature["Time"] = self.TimeDecFactor * dictFeature["Time"]
            dictFeature["sm__inst_executed.sum.per_second"] = self.IPSIncFactor * dictFeature["sm__inst_executed.sum.per_second"]
            dictFeature["sm__inst_executed.sum"] = self.IPSIncFactor * dictFeature["sm__inst_executed.sum"]

        sys.stdout.flush()
        # 检查是否停止运行
        try:
            self.isRun = QueueGlobal.get(block = False)
        except:
            pass
        if self.isRun == False:
            print("Manager Process: isRun = {}".format(self.isRun))
            return dictFeature, TEstimated

        return dictFeature, TEstimated

    def Init(self):
        global SMUtilTolerateFlag, SMUtil0_TolerateDuration, SMUsedDuraiton, SMUnusedDuraiton, SearchedOptGear, PredictedOptGear, CurrentGear

        self.isInit = EPOptDrv.ManagerInit(self.DeviceIDNVML, self.MEASURE_STOP_MODE["SIGNAL"])
        print("ManagerInit = {:d}".format(self.isInit))
        if self.isInit < 0:
            return

        self.SMClkGearCount = 103
        self.SMClkGearCount = int(EPOptDrv.GetSMClkGearCount() ) # 0, 1, 2, ..., SMClkGearCount-1
        self.NumGears = self.SMClkGearCount

        self.BaseSMClk = int(EPOptDrv.GetBaseSMClk())
        self.MinSMClk= int(EPOptDrv.GetMinSMClk())
        self.SMClkStep = int(EPOptDrv.GetSMClkStep())
        self.GPUName = EPOptDrv.GetGPUName()
        self.GPUName = self.GPUName.replace("NVIDIA","").replace("GeForce","").replace(" ","")
        self.BaseGear = int((self.BaseSMClk - self.MinSMClk) / self.SMClkStep)

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
        global SMUtilTolerateFlag, SMUtil0_TolerateDuration, SMUsedDuraiton, SMUnusedDuraiton, SearchedOptGear, PredictedOptGear, CurrentGear
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

        EPOptXGB.Init(self.QTableDir, self.GPUName)

        CurrentGear.value = self.NumGears

        TSimple = 0
        TFull = 0

        print("WorkMode: 开始工作模式")
        print("WatchSMUsed0: SMUtilTolerateFlag = {}".format(SMUtilTolerateFlag.value))

        PredictedOptGear.value = int(-1)
        SearchedOptGear.value = int(-1)
        while True:
            # wfr init isStateStable as True
            # if isStateStable is True, current loop is periodic, need detect period when gear changed, use runtime(T) as performace metric
            # if isStateStable is False, current loop is non-periodic, do not detect and use fixed peirod, use IPS as performace metric
            self.isStateStable = True
            # self.dequeT.clear()
            self.dequePower.clear()
            self.ResetTRange()

            self.MeasureUntilSMUsed()
            if self.isRun == False:
                return


            ConstraintDefault = -1.0
            ConstraintDefaultRef = -1.0
            if (self.Obj == "Energy" or self.Obj == "Performance") and False == self.IsSMUnusedPeriodly():
                EPOptDrv.ResetEnergyGear()
                dictFeatureDefault, TSimple = self.MeasureFeature("SIMPLE", True, StrictMode = "strict")
                if self.isRun == False:
                    return
                if False == self.TestSMUtil():
                    continue
                RewardDefault, ConstraintDefault = GetReward(dictFeatureDefault, self.Obj, True)
                if FLAG:
                    EPOptDrv.SetEnergyGear(self.BaseGear)
                dictFeatureBase, TSimple = self.MeasureFeature("SIMPLE", True, StrictMode = "strict")
                if self.isRun == False:
                    return
                if False == self.TestSMUtil():
                    continue
                self.SaveTPrev(TSimple, self.BaseGear)
                RewardBase, ConstraintBase = GetReward(dictFeatureBase, self.Obj, True)

                RewardDefaultRef = RewardDefault / RewardBase
                ConstraintDefaultRef = ConstraintDefault / ConstraintBase

            if PredictedOptGear.value < 0:

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

                # wfr 20210628 predict energy and time
                # ClockLowerBound = 390 # 2080Ti
                ClockLowerBound = 420 # 3080Ti
                tmpGearBegin = int((ClockLowerBound - self.MinSMClk) / self.SMClkStep)
                print("Predict: tmpGearBegin = {}".format(tmpGearBegin))
                arrayGear = np.arange(tmpGearBegin, self.NumGears+0.1, 1).astype(int)
                arrayClock = (self.MinSMClk + self.SMClkStep * arrayGear).astype(int)
                # ClockBase = self.MinSMClk + self.SMClkStep * self.BaseGear
                # print("WorkMode: before EPOptXGB.Predict")
                PredictedEnergy, PredictedTime = EPOptXGB.Predict(self.dictFeature, arrayClock, self.BaseSMClk)
                PredictedReward, PredictedConstraint = GetArrayReward(PredictedEnergy, PredictedTime, self.Obj)

                PredictedOptGear.value = SelectOptGear(arrayGear, PredictedReward, PredictedConstraint, ConstraintDefaultRef, self.Obj, self.Threshold)
                print("Optimization Object: {}".format(self.Obj))
                print("WorkMode: Predicted Opt Gear = {}".format(PredictedOptGear.value))

            if True == self.IsSMUnusedPeriodly():
                SearchedOptGear.value = PredictedOptGear.value

            if FLAG == False:
                PredictedOptGear.value = self.BaseGear

            if SearchedOptGear.value < 0:

                TimeStamp("Begin Local Search")
                print("Begin Local Search")

                # wfr 20210629 local search algorithm
                AllTryCount = 0
                arrayReward = -1 * np.ones(self.NumGears)
                arrayConstraint = -1 * np.ones(self.NumGears)
                arrayIPS = -1 * np.ones(self.NumGears)
                strIPS = "sm__inst_executed.sum.per_second"
                arrayEng = -1 * np.ones(self.NumGears)
                arrayInst = -1 * np.ones(self.NumGears)
                strInst = "sm__inst_executed.sum"

                # wfr 20210629 measure predicted opt gear
                CurrentGear.value = PredictedOptGear.value
                print("Set CurrentGear = {:d}".format(CurrentGear.value))
                if FLAG:
                    EPOptDrv.SetEnergyGear(CurrentGear.value)


                # if True or localStateStable == True:
                AllTryCount += 1
                if localStateStable == True:
                    print("WorkMode: 简测量 PredictedOptGear = {}".format(CurrentGear.value))
                    self.dictFeature, TSimple = self.MeasureFeature("SIMPLE", localStateStable, "relaxed")
                    if self.isRun == False:
                        return
                else:
                    print("WorkMode: 测量 IPS PredictedOptGear = {}".format(CurrentGear.value))
                    # self.dictFeature, TSimple = self.MeasureFeature("IPS", localStateStable, StrictMode = "normal")
                    self.dictFeature, TSimple = self.MeasureFeature("IPS", False, "external", TFull*PredictedTime[int(CurrentGear.value - tmpGearBegin)])
                    if self.isRun == False:
                        return
                    arrayIPS[CurrentGear.value] = self.dictFeature[strIPS]
                    arrayInst[CurrentGear.value] = self.dictFeature[strInst]
                    arrayEng[CurrentGear.value] = self.dictFeature["Energy"]
                if False == self.TestSMUtil():
                    continue
                self.SaveTPrev(TSimple, CurrentGear.value)
                print("dictFeature:")
                print(self.dictFeature)

                arrayReward[CurrentGear.value], arrayConstraint[CurrentGear.value] = GetReward(self.dictFeature, self.Obj, localStateStable)

                print("Optimization Object: {}".format(self.Obj))
                print("WorkMode: PredictedOptGear = {}; Reward = {}; Constraint = {}".format(CurrentGear.value, arrayReward[CurrentGear.value], arrayConstraint[CurrentGear.value]))

                
                # wfr 20210629 explore search range's upper bound
                radius = int(0.05 * self.NumGears)
                GearHighDone = False
                GearLowDone = False
                BetterFactor = 0.85
                GearHigh = PredictedOptGear.value

                if FLAG:
                    GearHighDone = True
                    GearLowDone = True
                    GearHigh = int(85 + radius)
                    GearLow = int(85 - radius)

                i = int(0)
                while GearHighDone == False:
                    i += int(1)
                    GearHigh = int(min((self.NumGears-1), (GearHigh + i * radius)))
                    CurrentGear.value = GearHigh
                    # print("Set CurrentGear = {:d}".format(CurrentGear.value))
                    if FLAG:
                        EPOptDrv.SetEnergyGear(CurrentGear.value)
                    TPrev, TNextPreference = self.EsimateTRange(CurrentGear.value)
                    AllTryCount += 1
                    if localStateStable == True:
                        print("WorkMode: 简测量 GearHigh = {}".format(CurrentGear.value))
                        self.dictFeature, TSimple = self.MeasureFeature("SIMPLE", localStateStable, "relaxed", TPrev, TNextPreference)
                        if self.isRun == False:
                            return
                    else:
                        print("WorkMode: 测量 IPS GearHigh = {}".format(CurrentGear.value))
                        # self.dictFeature, TSimple = self.MeasureFeature("IPS", localStateStable, "normal", TPrev, TNextPreference)
                        self.dictFeature, TSimple = self.MeasureFeature("IPS", False, "external", TFull*PredictedTime[int(CurrentGear.value - tmpGearBegin)])
                        if self.isRun == False:
                            return
                        arrayIPS[CurrentGear.value] = self.dictFeature[strIPS]
                        arrayInst[CurrentGear.value] = self.dictFeature[strInst]
                        arrayEng[CurrentGear.value] = self.dictFeature["Energy"]
                    if False == self.TestSMUtil():
                        break
                    self.SaveTPrev(TSimple, CurrentGear.value)
                    print("dictFeature:")
                    print(self.dictFeature)
                    arrayReward[CurrentGear.value], arrayConstraint[CurrentGear.value] = GetReward(self.dictFeature, self.Obj, localStateStable)
                    print("Optimization Object: {}".format(self.Obj))
                    print("WorkMode: GearHigh = {}; Reward = {}; Constraint = {}".format(CurrentGear.value, arrayReward[CurrentGear.value], arrayConstraint[CurrentGear.value]))


                    if GearHigh >= self.NumGears-1 or False == IsBetter(arrayReward[CurrentGear.value], arrayReward[PredictedOptGear.value], arrayConstraint[CurrentGear.value], arrayConstraint[PredictedOptGear.value], ConstraintDefault, self.Obj, self.Threshold):
                        print("WorkMode: 更新 GearHigh = {}".format(GearHigh))
                        break
                    elif True == IsBetter(arrayReward[CurrentGear.value], BetterFactor * arrayReward[PredictedOptGear.value], arrayConstraint[CurrentGear.value], arrayConstraint[PredictedOptGear.value], ConstraintDefault, self.Obj, self.Threshold):
                        GearLow = PredictedOptGear.value
                        GearLowDone = True
                        PredictedOptGear.value = CurrentGear.value
                        print("WorkMode: 更新 PredictedOptGear = {}".format(CurrentGear.value))
                        print("WorkMode: 更新 GearLow = {}".format(GearLow))
                        print("WorkMode: 更新 GearHigh = {}".format(GearHigh))
                    sys.stdout.flush()
                # end

                if False == self.TestSMUtil():
                    continue

                # wfr 20210629 explore search range's lower bound
                if GearLowDone == False:
                    GearLow = PredictedOptGear.value
                i = int(0)
                while GearLowDone == False:
                    i += int(1)
                    GearLow = int(max(tmpGearBegin, (GearLow - i * radius)))
                    CurrentGear.value = GearLow
                    # print("Set CurrentGear = {:d}".format(CurrentGear.value))
                    if FLAG:
                        EPOptDrv.SetEnergyGear(CurrentGear.value)
                    TPrev, TNextPreference = self.EsimateTRange(CurrentGear.value)
                    AllTryCount += 1
                    if localStateStable == True:
                        print("WorkMode: 简测量 GearLow = {}".format(CurrentGear.value))
                        self.dictFeature, TSimple = self.MeasureFeature("SIMPLE", localStateStable, "relaxed", TPrev, TNextPreference)
                        if self.isRun == False:
                            return
                    else:
                        print("WorkMode: 测量 IPS GearLow = {}".format(CurrentGear.value))
                        # self.dictFeature, TSimple = self.MeasureFeature("IPS", localStateStable, "normal", TPrev, TNextPreference)
                        self.dictFeature, TSimple = self.MeasureFeature("IPS", False, "external", TFull*PredictedTime[int(CurrentGear.value - tmpGearBegin)])
                        if self.isRun == False:
                            return
                        arrayIPS[CurrentGear.value] = self.dictFeature[strIPS]
                        arrayInst[CurrentGear.value] = self.dictFeature[strInst]
                        arrayEng[CurrentGear.value] = self.dictFeature["Energy"]
                    if False == self.TestSMUtil():
                        break
                    self.SaveTPrev(TSimple, CurrentGear.value)
                    print("dictFeature:")
                    print(self.dictFeature)
                    arrayReward[CurrentGear.value], arrayConstraint[CurrentGear.value] = GetReward(self.dictFeature, self.Obj, localStateStable)
                    print("Optimization Object: {}".format(self.Obj))
                    print("WorkMode: GearLow = {}; Reward = {}; Constraint = {}".format(CurrentGear.value, arrayReward[CurrentGear.value], arrayConstraint[CurrentGear.value]))


                    if GearLow <= tmpGearBegin or False == IsBetter(arrayReward[CurrentGear.value], arrayReward[PredictedOptGear.value], arrayConstraint[CurrentGear.value], arrayConstraint[PredictedOptGear.value], ConstraintDefault, self.Obj, self.Threshold):
                        print("WorkMode: 更新 GearLow = {}".format(GearLow))
                        break
                    elif True == IsBetter(arrayReward[CurrentGear.value], BetterFactor * arrayReward[PredictedOptGear.value], arrayConstraint[CurrentGear.value], arrayConstraint[PredictedOptGear.value], ConstraintDefault, self.Obj, self.Threshold):
                        GearHigh = PredictedOptGear.value
                        GearHighDone = True
                        PredictedOptGear.value = CurrentGear.value
                        print("WorkMode: 更新 PredictedOptGear = {}".format(CurrentGear.value))
                        print("WorkMode: 更新 GearLow = {}".format(GearLow))
                        print("WorkMode: 更新 GearHigh = {}".format(GearHigh))
                    sys.stdout.flush()
                # end
                
                if False == self.TestSMUtil():
                    continue

                # wfr 20210629 Golden-Section search
                Ratio = (1 + np.sqrt(5)) / 2 # golden ratio
                # init GearMiddle
                if GearHigh - PredictedOptGear.value > PredictedOptGear.value - GearLow:
                    GearMiddle = np.round(GearLow + Ratio / (1 + Ratio) * (GearHigh - GearLow)).astype(int)
                else:
                    GearMiddle = np.round(GearLow + 1 / (1 + Ratio) * (GearHigh - GearLow)).astype(int)
                
                # measure reward under GearMiddle
                CurrentGear.value = GearMiddle
                if arrayReward[CurrentGear.value] < 0:
                    if FLAG:
                        EPOptDrv.SetEnergyGear(CurrentGear.value)
                    TPrev, TNextPreference = self.EsimateTRange(CurrentGear.value)
                    AllTryCount += 1
                    if localStateStable == True:
                        print("WorkMode: 简测量 GearMiddle = {}".format(CurrentGear.value))
                        self.dictFeature, TSimple = self.MeasureFeature("SIMPLE", localStateStable, "relaxed", TPrev, TNextPreference)
                        if self.isRun == False:
                            return
                    else:
                        print("WorkMode: 测量 IPS GearMiddle = {}".format(CurrentGear.value))
                        # self.dictFeature, TSimple = self.MeasureFeature("IPS", localStateStable, "normal", TPrev, TNextPreference)
                        self.dictFeature, TSimple = self.MeasureFeature("IPS", False, "external", TFull*PredictedTime[int(CurrentGear.value - tmpGearBegin)])
                        if self.isRun == False:
                            return
                        arrayIPS[CurrentGear.value] = self.dictFeature[strIPS]
                        arrayInst[CurrentGear.value] = self.dictFeature[strInst]
                        arrayEng[CurrentGear.value] = self.dictFeature["Energy"]
                    if False == self.TestSMUtil():
                        continue
                    self.SaveTPrev(TSimple, CurrentGear.value)
                    print("dictFeature:")
                    print(self.dictFeature)                 
                    
                    arrayReward[CurrentGear.value], arrayConstraint[CurrentGear.value] = GetReward(self.dictFeature, self.Obj, localStateStable)
                    print("Optimization Object: {}".format(self.Obj))
                    print("WorkMode: GearMiddle = {}; Reward = {}; Constraint = {}".format(CurrentGear.value, arrayReward[CurrentGear.value], arrayConstraint[CurrentGear.value]))


                TryCount = 0
                while GearHigh - GearLow >= 3 and TryCount <= 5:
                    if GearHigh - GearMiddle > GearMiddle - GearLow:
                        GearTry = np.round(GearMiddle + 1 / (1 + Ratio) * (GearHigh - GearMiddle)).astype(int)
                    else:
                        GearTry = np.round(GearMiddle - 1 / (1 + Ratio) * (GearMiddle - GearLow)).astype(int)

                    # measure reward under GearTry
                    CurrentGear.value = GearTry
                    if arrayReward[CurrentGear.value] < 0:
                        if FLAG:
                            EPOptDrv.SetEnergyGear(CurrentGear.value)
                        TPrev, TNextPreference = self.EsimateTRange(CurrentGear.value)
                        AllTryCount += 1
                        if localStateStable == True:
                            print("WorkMode: 简测量 GearTry = {}".format(CurrentGear.value))
                            self.dictFeature, TSimple = self.MeasureFeature("SIMPLE", localStateStable, "relaxed", TPrev, TNextPreference)
                            if self.isRun == False:
                                return
                        else:
                            print("WorkMode: 测量 IPS GearTry = {}".format(CurrentGear.value))
                            # self.dictFeature, TSimple = self.MeasureFeature("IPS", localStateStable, "normal", TPrev, TNextPreference)
                            self.dictFeature, TSimple = self.MeasureFeature("IPS", False, "external", TFull*PredictedTime[int(CurrentGear.value - tmpGearBegin)])
                            if self.isRun == False:
                                return
                            arrayIPS[CurrentGear.value] = self.dictFeature[strIPS]
                            arrayInst[CurrentGear.value] = self.dictFeature[strInst]
                            arrayEng[CurrentGear.value] = self.dictFeature["Energy"]
                        if False == self.TestSMUtil():
                            break
                        self.SaveTPrev(TSimple, CurrentGear.value)
                        TryCount += 1
                        print("dictFeature:")
                        print(self.dictFeature)
                        
                        arrayReward[CurrentGear.value], arrayConstraint[CurrentGear.value] = GetReward(self.dictFeature, self.Obj, localStateStable)
                        print("Optimization Object: {}".format(self.Obj))
                        print("WorkMode: GearTry = {}; Reward = {}; Constraint = {}".format(CurrentGear.value, arrayReward[CurrentGear.value], arrayConstraint[CurrentGear.value]))

                    if True == IsBetter(arrayReward[GearTry], arrayReward[GearMiddle], arrayConstraint[GearTry], arrayConstraint[GearMiddle], ConstraintDefault, self.Obj, self.Threshold):
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

                if False == self.TestSMUtil():
                    continue

                # wfr 20210629 select optimal gear according to measured data
                tmpIndex = np.argwhere(arrayReward > 0)
                arrayAllGear = np.arange(self.NumGears).astype(int)
                tmpArrayGear = arrayAllGear[tmpIndex]
                tmpArrayReward = arrayReward[tmpIndex]
                tmpArrayConstraint = arrayConstraint[tmpIndex]
                tmpArrayIPS = arrayIPS[tmpIndex]
                # print("tmpIndex: {}".format(tmpIndex))
                # print("tmpArrayGear: {}".format(tmpArrayGear))
                # print("tmpArrayReward: {}".format(tmpArrayReward))
                # print("tmpArrayConstraint: {}".format(tmpArrayConstraint))
                SearchedOptGear.value = SelectOptGear(tmpArrayGear, tmpArrayReward, tmpArrayConstraint, ConstraintDefault, self.Obj, self.Threshold)
                CurrentGear.value = SearchedOptGear.value

                # wfr 20210818 remeasure abnormal IPS
                tmpIndexOpt = np.argwhere(SearchedOptGear.value == tmpArrayGear).flatten()[0]
                if localStateStable == False and tmpArrayIPS[tmpIndexOpt] > tmpArrayIPS[-1]:
                    print("remeasure abnormal IPS")
                    if FLAG:
                        EPOptDrv.SetEnergyGear(CurrentGear.value)
                    TPrev, TNextPreference = self.EsimateTRange(CurrentGear.value)
                    AllTryCount += 1
                    print("WorkMode: 测量 IPS GearAbnormal = {}".format(CurrentGear.value))
                    # self.dictFeature, TSimple = self.MeasureFeature("IPS", localStateStable, TPrev, TNextPreference)
                    self.dictFeature, TSimple = self.MeasureFeature("IPS", False, "external", TFull*PredictedTime[int(CurrentGear.value - tmpGearBegin)])
                    if self.isRun == False:
                        return
                    if False == self.TestSMUtil():
                        continue
                    self.SaveTPrev(TSimple, CurrentGear.value)
                    print("dictFeature:")
                    print(self.dictFeature)

                    arrayIPS[CurrentGear.value] = (self.dictFeature[strIPS] + arrayIPS[CurrentGear.value]) / 2
                    print("Mean IPS = {}".format(arrayIPS[CurrentGear.value]))
                    self.dictFeature[strIPS] = arrayIPS[CurrentGear.value]

                    arrayInst[CurrentGear.value] = (self.dictFeature[strInst] + arrayInst[CurrentGear.value]) / 2
                    print("Mean Inst = {}".format(arrayInst[CurrentGear.value]))
                    self.dictFeature[strInst] = arrayInst[CurrentGear.value]


                    arrayEng[CurrentGear.value] = (self.dictFeature["Energy"] + arrayEng[CurrentGear.value]) / 2
                    print("Mean Energy = {}".format(arrayEng[CurrentGear.value]))
                    self.dictFeature["Energy"] = arrayEng[CurrentGear.value]

                    arrayReward[CurrentGear.value], arrayConstraint[CurrentGear.value] = GetReward(self.dictFeature, self.Obj, localStateStable)
                    print("Optimization Object: {}".format(self.Obj))
                    print("WorkMode: GearAbnormal = {}; Reward = {}; Constraint = {}".format(CurrentGear.value, arrayReward[CurrentGear.value], arrayConstraint[CurrentGear.value]))

                    if self.isRun == False:
                        return

                    # wfr 20210629 select optimal gear according to measured data
                    tmpIndex = np.argwhere(arrayReward > 0)
                    arrayAllGear = np.arange(self.NumGears).astype(int)
                    tmpArrayGear = arrayAllGear[tmpIndex]
                    tmpArrayReward = arrayReward[tmpIndex]
                    tmpArrayConstraint = arrayConstraint[tmpIndex]
                    tmpArrayIPS = arrayIPS[tmpIndex]
                    # print("tmpIndex: {}".format(tmpIndex))
                    # print("tmpArrayGear: {}".format(tmpArrayGear))
                    # print("tmpArrayReward: {}".format(tmpArrayReward))
                    # print("tmpArrayConstraint: {}".format(tmpArrayConstraint))
                    SearchedOptGear.value = SelectOptGear(tmpArrayGear, tmpArrayReward, tmpArrayConstraint, ConstraintDefault, self.Obj, self.Threshold)
                    CurrentGear.value = SearchedOptGear.value
                if FLAG:
                    EPOptDrv.SetEnergyGear(CurrentGear.value)
                print("Local Search Try Count: {}".format(AllTryCount))
                print("Optimization Object: {}".format(self.Obj))
                for i in range(len(tmpIndex)):
                    print("Gear = {}; Reward = {}".format(tmpArrayGear[i], tmpArrayReward[i]))

                print("WorkMode: Searched OptGear = {}; Reward = {}; Constraint = {}".format(CurrentGear.value, arrayReward[CurrentGear.value], arrayConstraint[CurrentGear.value]))
                if self.Obj == "Energy":
                    tmpConstraint = (arrayConstraint[CurrentGear.value]-ConstraintDefault)/ConstraintDefault
                    print("ConstraintMeasured = {}; Constraint = {}".format(tmpConstraint, self.Threshold))
                elif self.Obj == "Performance":
                    tmpConstraint = (ConstraintDefault-arrayConstraint[CurrentGear.value])/ConstraintDefault
                    print("ConstraintMeasured = {}; Constraint = {}".format(tmpConstraint, self.Threshold))

            if FLAG == False:
                SearchedOptGear.value = self.BaseGear


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
        global SMUtilTolerateFlag, SMUtil0_TolerateDuration, SMUsedDuraiton, SMUnusedDuraiton, SearchedOptGear, PredictedOptGear, CurrentGear
        print("run: Manager Process")

        #进程ID
        PID = os.getpid()
        print("PyEPOpt.run(): PID = {:x}".format(PID))
        # 1 获取线程ID,NAME
        tmpThread = threading.currentThread()
        #线程ID
        print("PyEPOpt.run(): TID = {:x}".format(tmpThread.ident))

        # os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
        # os.environ["CUDA_VISIBLE_DEVICES"] = str(self.DeviceIDNVML)

        # 初始化
        self.Init()

        # wfr 20210826 start watch thread to handle SMUtil == 0
        # ThreadWatch = threading.Thread(target=EP_OPT.WatchSMUsed0, args=(self,))
        # ThreadWatch.start()

        # ProcessWatch = Process(target=WatchSMUsed0, args=(SMUtilTolerateFlag, SMUtil0_TolerateDuration, SMUsedDuraiton, SMUnusedDuraiton, SearchedOptGear, PredictedOptGear, CurrentGear, tmpList))
        ProcessWatch = Process(target=WatchSMUsed0, args=())
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
        # ThreadWatch.join()
        ProcessWatch.join()
        ProcessWatch.terminate()
        print("Manager Process: End")

    def Begin(self, inDeviceIDCUDADrv, inDeviceIDNVML, inRunMode="LEARN", inMeasureOutDir="NONE", inQTableDir="/home/wfr/work/Energy/EPOpt/QTable", inTestPrefix=""):
        global SMUtilTolerateFlag, SMUtil0_TolerateDuration, SMUsedDuraiton, SMUnusedDuraiton, SearchedOptGear, PredictedOptGear, CurrentGear

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
        self.QTableDir = inQTableDir
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
            self.listFeatureName = ["Energy", "Time"] + list(chain(*self.listMetricGroup))
            tmplist = [0.0] * len(self.listFeatureName)
            self.dictFeature = dict(zip(self.listFeatureName, tmplist))

            # 启动新进程
            print("before self.start()")
            self.start()
            print("after self.start()")
            time.sleep(3) # 延时 1s

            # 1. 初始化并启动测量线程（C++）
            self.isInit = EPOptDrv.MeasurerInit(self.DeviceIDCUDADrv, self.DeviceIDNVML, self.RunMode, self.MEASURE_STOP_MODE["SIGNAL"], self.listMetricGroup[0], self.MeasureDuration, self.isMeasurePower, self.isMeasurePerformace)

            # if self.isInit < 0:
            #     return

            # # 启动新进程
            # self.start()
        elif self.RunMode == self.RUN_MODE["MEASURE"]:
            self.DeviceIDCUDADrv = inDeviceIDCUDADrv
            self.DeviceIDNVML = inDeviceIDNVML
            self.MeasureOutDir = inMeasureOutDir

            self.listMetricGroup, self.listMetricIPS = SetMetric(True, self.GPUName)
            self.listFeatureName = ["Energy", "Time"] + list(chain(*self.listMetricGroup))
            tmplist = [0.0] * len(self.listFeatureName)
            self.dictFeature = dict(zip(self.listFeatureName, tmplist))

            self.isInit = EPOptDrv.MeasurerInitInCode(self.DeviceIDCUDADrv, self.DeviceIDNVML, self.RunMode, self.listMetricGroup[0], self.isMeasurePower, self.isMeasurePerformace)
            # EPOptDrv.MeasurerBeginInCode()

    def End(self):

        global QueueGlobal, QueueGlobalWatch
        global SMUtilTolerateFlag, SMUtil0_TolerateDuration, SMUsedDuraiton, SMUnusedDuraiton, SearchedOptGear, PredictedOptGear, CurrentGear

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
            self.join() # 等待频率调节进程结束, 0 表示不等待立即结束子进程
            self.terminate()
            print("End wait join: {0}s".format(time.time()-start))
            sys.stdout.flush()

            # start = time.time()
            EPOptDrv.MeasurerStop()
            # print("End wait MeasurerStop: {0}s".format(time.time()-start))

            print("Measurer Thread: End")
            sys.stdout.flush()
        elif self.RunMode == self.RUN_MODE["MEASURE"]:
            listMetric = EPOptDrv.MeasurerEndInCode()

            # print("listMetric:")
            # print(listMetric)

            # 将测量结果存入字典
            print("PyEPOpt.End(): len(listMetric) = {}".format(len(listMetric)))
            # for i in range(len(listMetric)):
            #     self.dictFeature[listMetric[i][0]] = listMetric[i][1]
            self.dictFeature = listMetric

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

