# -*- coding: utf-8 -*-
# StateReward.py

# wfr 20210601
import importlib, sys
importlib.reload(sys)
# sys.setdefaultencoding('utf8')

# wfr 20201109
# import pandas as pd
import math
import numpy as np
import os
import copy

# wfr 20210708 judge A is better than B or not
def IsBetter(Rewaed_A, Rewaed_B, Constraint_A=-1.0, Constraint_B=-1.0, ConstraintDefault=-1.0, Obj="ED2P", threshold=0.05):
    
    flag = False

    if Obj == "EDP" or Obj == "ED2P":
        if Rewaed_A < Rewaed_B:
            flag = True

    elif Obj == "Energy": # within performance loss contraint and optimize energy
        Thres_A = (Constraint_A-ConstraintDefault)/ConstraintDefault
        Thres_B = (Constraint_B-ConstraintDefault)/ConstraintDefault
        
        # 都满足约束时, 能耗低的更好
        if Thres_A <= threshold and Thres_B <= threshold and Rewaed_A < Rewaed_B:
            flag = True

        # 都不满足约束时, 更接近约束的更好
        elif Thres_A > threshold and Thres_B > threshold and Thres_A < Thres_B:
            flag = True

        # 满足约束的更好
        elif Thres_A <= threshold and Thres_B > threshold:
            flag = True

    elif Obj == "Performance": # over energy save contraint and optimize Performance
        Thres_A = (ConstraintDefault-Constraint_A)/ConstraintDefault
        Thres_B = (ConstraintDefault-Constraint_B)/ConstraintDefault
        
        # 都满足约束时, 运行时间短的更好
        if Thres_A >= threshold and Thres_B >= threshold and Rewaed_A < Rewaed_B:
            flag = True
        
        # 都不满足约束时, 更接近约束的更好
        elif Thres_A < threshold and Thres_B < threshold and Thres_A > Thres_B:
            flag = True
        
        # 满足约束的更好
        elif Thres_A >= threshold and Thres_B < threshold:
            flag = True

    return flag

def SelectOptGear(arrayGear, arrayReward, arrayConstraint=[], ConstraintRef=-1.0, Obj="ED2P", threshold=0.05):
    OptGear = 70
    if Obj == "EDP" or Obj == "ED2P":
        tmpIndex = np.argwhere(np.min(arrayReward) == arrayReward).flatten()[0]
        OptGear = arrayGear[tmpIndex]

    elif Obj == "Energy":
        arrayPerfLoss = (arrayConstraint - ConstraintRef) / ConstraintRef
        tmpIndex = np.argwhere(arrayPerfLoss <= threshold).flatten()
        # wfr 20210708 如果不能满足约束, 则找到最接近约束的
        if len(tmpIndex) <= 0:
            tmpIndex = np.argwhere(np.min(arrayPerfLoss) == arrayPerfLoss).flatten()

        arrayGearMeet = arrayGear[tmpIndex]
        arrayRewardMeet = arrayReward[tmpIndex]
        tmpIndex = np.argwhere(np.min(arrayRewardMeet) == arrayRewardMeet).flatten()[0]
        OptGear = arrayGearMeet[tmpIndex]

    elif Obj == "Time":
        arrayEngSave = (ConstraintRef - arrayConstraint) / ConstraintRef
        tmpIndex = np.argwhere(arrayEngSave >= threshold).flatten()
        # wfr 20210708 如果不能满足约束, 则找到最接近约束的
        if len(tmpIndex) <= 0:
            tmpIndex = np.argwhere(np.max(arrayEngSave) == arrayEngSave).flatten()

        arrayGearMeet = arrayGear[tmpIndex]
        arrayRewardMeet = arrayReward[tmpIndex]
        tmpIndex = np.argwhere(np.min(arrayRewardMeet) == arrayRewardMeet).flatten()[0]
        OptGear = arrayGearMeet[tmpIndex]

    return int(OptGear)

def SetMetric(isMeasure, GPUName):

    # tmpDir = os.path.abspath(__file__)
    # tmpDir = os.path.split(tmpDir)[0]
    # # print("tmpDir = {}".format(tmpDir))
    # MetricDir = os.path.abspath(tmpDir)

    MetricDir = "/home/wfr/work/Energy/EPOpt"
    # MetricNameFileDir = "/home/wfr/work/Energy/EPOpt/Src"
    if isMeasure == True:
        MetricNameFileDir = os.path.join(MetricDir, "Metric.conf")
    else:
        MetricNameFileDir = os.path.join(MetricDir, "MetricFull-"+GPUName+".conf")

    listMetricGroup = []
    listMetricName = []

    # wfr 20210518 read metric name from file
    with open(MetricNameFileDir, "r") as PerfFile:
        DataList = PerfFile.readlines()

        for DataLine in DataList:

            if DataLine[0] == "#":
                continue
            elif DataLine[0] == ";":
                if len(listMetricName) > 0:
                    listMetricGroup.append(copy.deepcopy(listMetricName))
                    listMetricName = []
                continue

            tmpStr = "#"
            pos0 = DataLine.find(tmpStr)
            if pos0 >= 0:
                MetricName = DataLine[:pos0].strip()
            else:
                MetricName = DataLine.strip()

            if len(MetricName) > 0:
                listMetricName.append(copy.deepcopy(MetricName))

        if len(listMetricName) > 0:
            listMetricGroup.append(copy.deepcopy(listMetricName))
            listMetricName = []
    
    listMetricIPS = []
    listMetricIPS.append("sm__inst_executed.sum")
    listMetricIPS.append("sm__inst_executed.sum.per_second")
    # listMetricIPS.append("sm__thread_inst_executed_pred_on_realtime.sum")
    # listMetricIPS.append("sm__thread_inst_executed_pred_on_realtime.sum.per_second")
    # listMetricIPS.append("smsp__thread_inst_executed_pred_on.sum")
    # listMetricIPS.append("smsp__thread_inst_executed_pred_on.sum.per_second")

    
    

    # listMetricName = []

    # # wfr 20201030 初步确定的特征, 可以在一次运行中全都收集
    # listMetricName.append("sm__inst_executed.sum") # 指令数
    # listMetricName.append("sm__inst_executed.sum.pct_of_peak_sustained_active") # IPC 达到上限的百分比 已平均
    # listMetricName.append("sm__inst_executed.sum.per_second") # 每秒平均指令数 已平均
    # # listMetricName.append("lts__t_request_hit_rate.pct") # L2Cache 请求命中率 已平均
    # # listMetricName.append("lts__t_requests.sum") # L2Cache 请求数 需平均
    # listMetricName.append("sm__cycles_active.avg") # 需平均
    # listMetricName.append("gpu__cycles_active.avg") # 需平均

    # listMetricName.append("l1tex__t_sector_hit_rate.pct")
    # listMetricName.append("l1tex__t_sectors_lookup_miss.sum")
    # listMetricName.append("lts__t_sector_hit_rate.pct")
    # listMetricName.append("lts__t_sectors_lookup_miss.sum")

    # listMetricName.append("sm__inst_executed_pipe_tensor.sum")
    # listMetricName.append("sm__inst_executed_pipe_tensor.sum.pct_of_peak_sustained_active")


    # listMetricName.append("sm__inst_executed_pipe_adu.sum")
    # listMetricName.append("sm__inst_executed_pipe_adu.sum.pct_of_peak_sustained_active")
    # listMetricName.append("sm__inst_executed_pipe_fma.sum")
    # listMetricName.append("sm__inst_executed_pipe_fma.sum.pct_of_peak_sustained_active")
    # listMetricName.append("sm__inst_executed_pipe_alu.sum")
    # listMetricName.append("sm__inst_executed_pipe_alu.sum.pct_of_peak_sustained_active")


    # listMetricName.append("sm__inst_executed_pipe_fp16.sum")
    # listMetricName.append("sm__inst_executed_pipe_fp16.sum.pct_of_peak_sustained_active")
    # listMetricName.append("sm__inst_executed_pipe_fp64.sum")
    # listMetricName.append("sm__inst_executed_pipe_fp64.sum.pct_of_peak_sustained_active")
    # listMetricName.append("sm__inst_executed_pipe_xu.sum")
    # listMetricName.append("sm__inst_executed_pipe_xu.sum.pct_of_peak_sustained_active")
    # listMetricName.append("sm__inst_executed_pipe_tex.sum")
    # listMetricName.append("sm__inst_executed_pipe_tex.sum.pct_of_peak_sustained_active")


    # listMetricName.append("sm__inst_executed_pipe_cbu.sum")
    # listMetricName.append("sm__inst_executed_pipe_cbu.sum.pct_of_peak_sustained_active")
    # listMetricName.append("sm__inst_executed_pipe_ipa.sum")
    # listMetricName.append("sm__inst_executed_pipe_ipa.sum.pct_of_peak_sustained_active")
    # listMetricName.append("sm__inst_executed_pipe_lsu.sum")
    # listMetricName.append("sm__inst_executed_pipe_lsu.sum.pct_of_peak_sustained_active")
    # listMetricName.append("sm__inst_executed_pipe_uniform.sum")
    # listMetricName.append("sm__inst_executed_pipe_uniform.sum.pct_of_peak_sustained_active")

    # wfr 20201021 为了测量不同计算指令出现的频次并排序

    ## listMetricName.append("sm__inst_executed.sum.per_cycle_active") # IPC 已平均

    # return listMetricName
    # print("listMetricGroup:")
    # print(listMetricGroup)
    return listMetricGroup, listMetricIPS

def GetAvgFeature(dictFeature, TCount):

    dictFeature["Energy"] = dictFeature["Energy"] / TCount
    dictFeature["Time"] = dictFeature["Time"] / TCount
    if len(dictFeature) > 2:
        dictFeature["sm__inst_executed.sum"] = dictFeature["sm__inst_executed.sum"] / TCount
        dictFeature["lts__t_requests.sum"] = dictFeature["lts__t_requests.sum"] / TCount
        dictFeature["sm__cycles_active.avg"] = dictFeature["sm__cycles_active.avg"] / TCount
        dictFeature["gpu__cycles_active.avg"] = dictFeature["gpu__cycles_active.avg"] / TCount

    return dictFeature

def GetState(dictFeature):

    IPCPercentScale = 1.2
    CacheMissPerInstScale = 2.5 * 100 # CacheMissPerInst 的调节系数
    # 10 * 10

    IPCPercent = dictFeature["sm__inst_executed.sum.pct_of_peak_sustained_active"] * IPCPercentScale
    if np.abs(IPCPercent) < 1e-12:
        CacheMissPerInst = 0
    else:
        CacheMissPerInst = (1 - dictFeature["lts__t_request_hit_rate.pct"]/100) * dictFeature["lts__t_requests.sum"] / dictFeature["sm__inst_executed.sum"] * CacheMissPerInstScale # 乘调节系数

    if np.abs(dictFeature["gpu__cycles_active.avg"]) < 1e-12:
        SMActiveCyclePercent = 0
    else:
        SMActiveCyclePercent = dictFeature["sm__cycles_active.avg"] / dictFeature["gpu__cycles_active.avg"] * 100

    if IPCPercent >= 100:
        print("IPCPercent = {:.2f}".format(IPCPercent))
        IPCPercent = 99.9
        print("Set IPCPercent = 99.9")
    if CacheMissPerInst >= 100:
        print("CacheMissPerInst = {:.2f}".format(CacheMissPerInst))
        CacheMissPerInst = 99.9
        print("Set CacheMissPerInst = 99.9")
    if SMActiveCyclePercent >= 100:
        print("SMActiveCyclePercent = {:.2f}".format(SMActiveCyclePercent))
        SMActiveCyclePercent = 99.9
        print("Set SMActiveCyclePercent = 99.9")

    State = np.array([IPCPercent, CacheMissPerInst, SMActiveCyclePercent])

    return State

def GetArrayReward(arrayEnergy, arrayTime, Obj="ED2P"):
    arrayConstraint = []
    if Obj == "EDP":
        arrayReward = arrayEnergy * arrayTime
    elif Obj == "ED2P":
        arrayReward = arrayEnergy * arrayTime * arrayTime
    elif Obj == "Energy":
        arrayReward = arrayEnergy
        arrayConstraint = arrayTime
    elif Obj == "Performance":
        arrayReward = arrayTime
        arrayConstraint = arrayEnergy
    else:
        arrayReward = arrayEnergy * arrayTime * arrayTime

    return arrayReward, arrayConstraint

def GetReward(dictFeature, Obj="ED2P", isStateStable=True):

    # wfr 20210818 modify 0 value
    if "sm__inst_executed.sum.per_second" in dictFeature.keys() and dictFeature["sm__inst_executed.sum.per_second"] < 1e-9:
        dictFeature["sm__inst_executed.sum.per_second"] = 1e12
    if "sm__inst_executed.sum" in dictFeature.keys() and dictFeature["sm__inst_executed.sum"] < 1e-9:
        dictFeature["sm__inst_executed.sum"] = dictFeature["sm__inst_executed.sum.per_second"] * dictFeature["Time"]

    Constraint = -1.0
    if Obj == "EDP":
        if isStateStable == True:
            Reward = dictFeature["Energy"] * dictFeature["Time"]
        else:
            IPSScale = 1e10 # IPS 的调节系数
            PowerScale = 1
            RewardScale = 1
            Reward = RewardScale / (pow( (dictFeature["sm__inst_executed.sum.per_second"] / IPSScale), 2 ) / ( (dictFeature["Energy"] / dictFeature["Time"]) * PowerScale ))

    elif Obj == "ED2P":
        if isStateStable == True:
            Reward = dictFeature["Energy"] * dictFeature["Time"] * dictFeature["Time"]
        else:
            IPSScale = 1e10 # IPS 的调节系数
            PowerScale = 1
            RewardScale = 10
            Reward = RewardScale / (pow( (dictFeature["sm__inst_executed.sum.per_second"] / IPSScale), 3 ) / ( (dictFeature["Energy"] / dictFeature["Time"]) * PowerScale ))

    elif Obj == "Energy":
        if isStateStable == True:
            Reward = dictFeature["Energy"]
            Constraint = dictFeature["Time"]
        else:
            NumInst = 1e13
            Reward = NumInst * dictFeature["Energy"] / dictFeature["sm__inst_executed.sum"]
            Constraint = NumInst / dictFeature["sm__inst_executed.sum.per_second"]

    elif Obj == "Time":
        if isStateStable == True:
            Reward = dictFeature["Time"]
            Constraint = dictFeature["Energy"]
        else:
            NumInst = 1e13
            Reward = NumInst / dictFeature["sm__inst_executed.sum.per_second"]
            Constraint = NumInst * dictFeature["Energy"] / dictFeature["sm__inst_executed.sum"]

    else:
        if isStateStable == True:
            Reward = dictFeature["Energy"] * dictFeature["Time"] * dictFeature["Time"]
        else:
            IPSScale = 1e10 # IPS 的调节系数
            PowerScale = 1
            RewardScale = 10
            Reward = RewardScale / (pow( (dictFeature["sm__inst_executed.sum.per_second"] / IPSScale), 3 ) / ( (dictFeature["Energy"] / dictFeature["Time"]) * PowerScale ))
    
    return Reward, Constraint
