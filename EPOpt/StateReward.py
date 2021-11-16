# -*- coding: utf-8 -*-
# StateReward.py

# wfr 20210601
import importlib, sys
importlib.reload(sys)

# wfr 20201109
import sys
import numpy as np
import os
import copy

# wfr 20210708 judge A is better than B or not
def IsBetter(Rewaed_A, Rewaed_B, Constraint_A=-1.0, Constraint_B=-1.0, Obj="ED2P", threshold=0.05):
    
    flag = False
    # ConstraintDefault = 1.0 # wfr 20211021 以 NVIDIA 驱动默认策略为基准, 即 1.0
    if Obj == "EDP" or Obj == "ED2P":
        if Rewaed_A < Rewaed_B:
            flag = True

    elif Obj == "Energy": # within performance loss contraint and optimize energy
        # Thres_A = (Constraint_A-ConstraintDefault)/ConstraintDefault
        # Thres_B = (Constraint_B-ConstraintDefault)/ConstraintDefault
        Thres_A = Constraint_A
        Thres_B = Constraint_B
        
        # 都满足约束时, 能耗低的更好
        if Thres_A <= threshold and Thres_B <= threshold and Rewaed_A < Rewaed_B:
            flag = True

        # 都不满足约束时, 更接近约束的更好(运行时间开销小的更好)
        elif Thres_A > threshold and Thres_B > threshold and Thres_A < Thres_B:
            flag = True

        # 满足约束的更好
        elif Thres_A <= threshold and Thres_B > threshold:
            flag = True

    elif Obj == "Performance": # over energy save contraint and optimize Performance
        # Thres_A = (ConstraintDefault-Constraint_A)/ConstraintDefault
        # Thres_B = (ConstraintDefault-Constraint_B)/ConstraintDefault
        Thres_A = Constraint_A
        Thres_B = Constraint_B
        
        # 都满足约束时, 运行时间短的更好
        if Thres_A >= threshold and Thres_B >= threshold and Rewaed_A < Rewaed_B:
            flag = True
        
        # 都不满足约束时, 更接近约束的更好(更节能的更好)
        elif Thres_A < threshold and Thres_B < threshold and Thres_A > Thres_B:
            flag = True
        
        # 满足约束的更好
        elif Thres_A >= threshold and Thres_B < threshold:
            flag = True

    return flag

def SelectOptGear(arrayGear, arrayReward, arrayConstraint=[], Obj="ED2P", threshold=0.05):

    # ConstraintRef = 1 # wfr 20211021 以 NVIDIA 驱动默认策略为基准, 即 1.0
    OptGear = 70
    arrayGearMeet = np.array([])
    arrayRewardMeet = np.array([])
    if Obj == "EDP" or Obj == "ED2P":
        tmpIndex = np.argmin(arrayReward)
        OptGear = arrayGear[tmpIndex]

    elif Obj == "Energy":
        # arrayPerfLoss = (arrayConstraint - ConstraintRef) / ConstraintRef
        arrayPerfLoss = arrayConstraint
        tmpIndex = np.argwhere(arrayPerfLoss <= threshold).flatten()
        # wfr 20210708 如果不能满足约束, 则找到最接近约束的
        if len(tmpIndex) <= 0:
            # tmpIndex = np.argmin(arrayPerfLoss)
            # OptGear = arrayGear[tmpIndex]
            OptGear = np.max(arrayGear)
        else:
            arrayGearMeet = arrayGear[tmpIndex]
            arrayRewardMeet = arrayReward[tmpIndex]
            tmpIndex = np.argmin(arrayRewardMeet)
            OptGear = arrayGearMeet[tmpIndex]

    elif Obj == "Performance":
        # arrayEngSave = (ConstraintRef - arrayConstraint) / ConstraintRef
        arrayEngSave = arrayConstraint
        tmpIndex = np.argwhere(arrayEngSave >= threshold).flatten()
        # wfr 20210708 如果不能满足约束, 则找到最接近约束的
        if len(tmpIndex) <= 0:
            tmpIndex = np.argmax(arrayEngSave).flatten()
            OptGear = arrayGear[tmpIndex]
        else:
            arrayGearMeet = arrayGear[tmpIndex]
            arrayRewardMeet = arrayReward[tmpIndex]
            tmpIndex = np.argmin(arrayRewardMeet)
            OptGear = arrayGearMeet[tmpIndex]

    print("SelectOptGear: arrayGear = {}".format(arrayGear))
    print("SelectOptGear: arrayReward = {}".format(arrayReward))
    print("SelectOptGear: arrayConstraint = {}".format(arrayConstraint))
    print("SelectOptGear: arrayRewardMeet = {}".format(arrayRewardMeet))
    print("SelectOptGear: arrayGearMeet = {}".format(arrayGearMeet))
    print("SelectOptGear: tmpIndex = {}".format(tmpIndex))
    print("SelectOptGear: OptGear = {}".format(OptGear))
    sys.stdout.flush()

    return int(OptGear)

def SetMetric(isMeasure, GPUName):

    # tmpDir = os.path.abspath(__file__)
    # tmpDir = os.path.split(tmpDir)[0]
    # # print("tmpDir = {}".format(tmpDir))
    # MetricDir = os.path.abspath(tmpDir)

    MetricDir = "./"
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
    listMetricIPS.append("sm__cycles_active.avg")
    listMetricIPS.append("sm__cycles_elapsed.avg")
    # return listMetricName
    # print("listMetricGroup:")
    # print(listMetricGroup)
    return listMetricGroup, listMetricIPS

def GetArrayReward(arrayEnergy, arrayTime, Obj="ED2P", ConstraintDefault=1.0):
    arrayConstraint = np.array([])
    if Obj == "EDP":
        arrayReward = arrayEnergy * arrayTime
    elif Obj == "ED2P":
        arrayReward = arrayEnergy * arrayTime * arrayTime
    elif Obj == "Energy":
        # arrayReward = arrayEnergy
        arrayReward = arrayEnergy * arrayTime * arrayTime
        arrayConstraint = (arrayTime - ConstraintDefault) / ConstraintDefault
    elif Obj == "Performance":
        arrayReward = arrayTime
        arrayConstraint = (ConstraintDefault - arrayEnergy) / ConstraintDefault
    else:
        arrayReward = arrayEnergy * arrayTime * arrayTime

    print("GetArrayReward: arrayEnergy = {}".format(arrayEnergy))
    print("GetArrayReward: arrayTime = {}".format(arrayTime))
    print("GetArrayReward: Obj = {}".format(Obj))
    print("GetArrayReward: ConstraintDefault = {}".format(ConstraintDefault))
    print("GetArrayReward: arrayReward = {}".format(arrayReward))
    print("GetArrayReward: arrayConstraint = {}".format(arrayConstraint))
    sys.stdout.flush()

    return arrayReward, arrayConstraint

# wfr 20211030 周期不稳定时
def GetArrayRewardIPS(arrayEnergy, arrayTime, arrayIPS, arrayInst, Obj, ConstraintDefault=1.0):
    arrayIPS[arrayIPS<1e-9] = 1e12
    arrayInst[arrayInst<1e-9] = arrayInst[arrayInst<1e-9] * arrayTime[arrayInst<1e-9]

    Constraint = -1.0 * np.ones(len(arrayEnergy))
    if Obj == "EDP":
        IPSScale = 1e10 # IPS 的调节系数
        PowerScale = 1
        RewardScale = 1
        # IPSActive = dictFeature["sm__inst_executed.sum.per_second"] / (dictFeature["sm__cycles_active.avg"]/dictFeature["sm__cycles_elapsed.avg"])
        IPSActive = arrayIPS
        Reward = RewardScale / ( (IPSActive / IPSScale)**2 / ( (arrayEnergy / arrayTime) * PowerScale ) )
    elif Obj == "ED2P":
        IPSScale = 1e10 # IPS 的调节系数
        PowerScale = 1
        RewardScale = 10
        # IPSActive = dictFeature["sm__inst_executed.sum.per_second"] / (dictFeature["sm__cycles_active.avg"]/dictFeature["sm__cycles_elapsed.avg"])
        IPSActive = arrayIPS
        Reward = RewardScale / ( (IPSActive / IPSScale)**3 / ( (arrayEnergy / arrayTime) * PowerScale ) )
    elif Obj == "Energy":

        IPSScale = 1e10 # IPS 的调节系数
        PowerScale = 1
        RewardScale = 10
        # IPSActive = dictFeature["sm__inst_executed.sum.per_second"] / (dictFeature["sm__cycles_active.avg"]/dictFeature["sm__cycles_elapsed.avg"])
        IPSActive = arrayIPS
        Reward = RewardScale / ( (IPSActive / IPSScale)**3 / ( (arrayEnergy / arrayTime) * PowerScale ) )

        NumInst = 1e13
        # Reward = NumInst * arrayEnergy / arrayInst
        # IPSActive = dictFeature["sm__inst_executed.sum.per_second"] / (dictFeature["sm__cycles_active.avg"]/dictFeature["sm__cycles_elapsed.avg"])
        IPSActive = arrayIPS
        Constraint = ((NumInst / IPSActive) - ConstraintDefault) / ConstraintDefault
    elif Obj == "Performance":
        NumInst = 1e13
        # IPSActive = dictFeature["sm__inst_executed.sum.per_second"] / (dictFeature["sm__cycles_active.avg"]/dictFeature["sm__cycles_elapsed.avg"])
        IPSActive = arrayIPS
        Reward = NumInst / IPSActive
        Constraint = (ConstraintDefault - (NumInst * arrayEnergy / arrayInst)) / ConstraintDefault
    else:
        IPSScale = 1e10 # IPS 的调节系数
        PowerScale = 1
        RewardScale = 10
        # IPSActive = dictFeature["sm__inst_executed.sum.per_second"] / (dictFeature["sm__cycles_active.avg"]/dictFeature["sm__cycles_elapsed.avg"])
        IPSActive = arrayIPS
        Reward = RewardScale / ( (IPSActive / IPSScale)**3 / ( (arrayEnergy / arrayTime) * PowerScale ) )

    print("GetArrayRewardIPS: arrayEnergy = {}".format(arrayEnergy))
    print("GetArrayRewardIPS: arrayTime = {}".format(arrayTime))
    print("GetArrayRewardIPS: Obj = {}".format(Obj))
    print("GetArrayRewardIPS: ConstraintDefault = {}".format(ConstraintDefault))
    print("GetArrayRewardIPS: Reward = {}".format(Reward))
    print("GetArrayRewardIPS: Constraint = {}".format(Constraint))
    sys.stdout.flush()

    return Reward, Constraint

def GetReward(dictFeature, Obj="ED2P", isStateStable=True, ConstraintDefault=1.0):

    # wfr 20210818 modify 0 value
    if "sm__inst_executed.sum.per_second" in dictFeature.keys() and dictFeature["sm__inst_executed.sum.per_second"] < 1e-9:
        dictFeature["sm__inst_executed.sum.per_second"] = 1e12
    if "sm__inst_executed.sum" in dictFeature.keys() and dictFeature["sm__inst_executed.sum"] < 1e-9:
        dictFeature["sm__inst_executed.sum"] = dictFeature["sm__inst_executed.sum.per_second"] * dictFeature["Time"]

    # dictFeature["Power"] = dictFeature["Power"] - PowerThreshold
    # dictFeature["Energy"] = dictFeature["Power"] * dictFeature["Time"]

    Constraint = -1.0
    if Obj == "EDP":
        if isStateStable == True:
            Reward = dictFeature["Energy"] * dictFeature["Time"]
        else:
            IPSScale = 1e10 # IPS 的调节系数
            PowerScale = 1
            RewardScale = 1
            # IPSActive = dictFeature["sm__inst_executed.sum.per_second"] / (dictFeature["sm__cycles_active.avg"]/dictFeature["sm__cycles_elapsed.avg"])
            IPSActive = dictFeature["sm__inst_executed.sum.per_second"]
            Reward = RewardScale / ( pow( IPSActive / IPSScale, 2 ) / ( (dictFeature["Energy"] / dictFeature["Time"]) * PowerScale ) )

    elif Obj == "ED2P":
        if isStateStable == True:
            Reward = dictFeature["Energy"] * dictFeature["Time"] * dictFeature["Time"]
        else:
            IPSScale = 1e10 # IPS 的调节系数
            PowerScale = 1
            RewardScale = 10
            # IPSActive = dictFeature["sm__inst_executed.sum.per_second"] / (dictFeature["sm__cycles_active.avg"]/dictFeature["sm__cycles_elapsed.avg"])
            IPSActive = dictFeature["sm__inst_executed.sum.per_second"]
            Reward = RewardScale / ( pow( IPSActive / IPSScale, 3 ) / ( (dictFeature["Energy"] / dictFeature["Time"]) * PowerScale ) )

    elif Obj == "Energy":
        if isStateStable == True:
            # Reward = dictFeature["Energy"]
            Reward = dictFeature["Energy"] * dictFeature["Time"] * dictFeature["Time"]
            Constraint = (dictFeature["Time"] - ConstraintDefault) / ConstraintDefault
        else:
            IPSScale = 1e10 # IPS 的调节系数
            PowerScale = 1
            RewardScale = 10
            # IPSActive = dictFeature["sm__inst_executed.sum.per_second"] / (dictFeature["sm__cycles_active.avg"]/dictFeature["sm__cycles_elapsed.avg"])
            IPSActive = dictFeature["sm__inst_executed.sum.per_second"]
            Reward = RewardScale / ( pow( IPSActive / IPSScale, 3 ) / ( (dictFeature["Energy"] / dictFeature["Time"]) * PowerScale ) )

            NumInst = 1e13
            # Reward = NumInst * dictFeature["Energy"] / dictFeature["sm__inst_executed.sum"]
            # IPSActive = dictFeature["sm__inst_executed.sum.per_second"] / (dictFeature["sm__cycles_active.avg"]/dictFeature["sm__cycles_elapsed.avg"])
            IPSActive = dictFeature["sm__inst_executed.sum.per_second"]
            Constraint = ((NumInst / IPSActive) - ConstraintDefault) / ConstraintDefault

    elif Obj == "Performance":
        if isStateStable == True:
            Reward = dictFeature["Time"]
            Constraint = (ConstraintDefault - dictFeature["Energy"]) / ConstraintDefault
        else:
            NumInst = 1e13
            # IPSActive = dictFeature["sm__inst_executed.sum.per_second"] / (dictFeature["sm__cycles_active.avg"]/dictFeature["sm__cycles_elapsed.avg"])
            IPSActive = dictFeature["sm__inst_executed.sum.per_second"]
            Reward = NumInst / IPSActive
            Constraint = (ConstraintDefault - (NumInst * dictFeature["Energy"] / dictFeature["sm__inst_executed.sum"])) / ConstraintDefault

    else:
        if isStateStable == True:
            Reward = dictFeature["Energy"] * dictFeature["Time"] * dictFeature["Time"]
        else:
            IPSScale = 1e10 # IPS 的调节系数
            PowerScale = 1
            RewardScale = 10
            # IPSActive = dictFeature["sm__inst_executed.sum.per_second"] / (dictFeature["sm__cycles_active.avg"]/dictFeature["sm__cycles_elapsed.avg"])
            IPSActive = dictFeature["sm__inst_executed.sum.per_second"]
            Reward = RewardScale / ( pow( IPSActive / IPSScale, 3 ) / ( (dictFeature["Energy"] / dictFeature["Time"]) * PowerScale ) )
    
    print("GetReward: Obj = {}".format(Obj))
    print("GetReward: ConstraintDefault = {}".format(ConstraintDefault))
    print("GetReward: Reward = {}".format(Reward))
    print("GetReward: Constraint = {}".format(Constraint))
    sys.stdout.flush()

    return Reward, Constraint
