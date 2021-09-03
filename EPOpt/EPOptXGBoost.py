# import time
import os
import numpy as np
import xgboost as xgb

class EP_OPT_XGBOOST():

    def __init__(self):
        self.ClockBegin0 = int(-1)
        self.ClockEnd0 = int(1019)
        self.ClockBegin1 = int(1020)
        self.ClockEnd1 = int(1424)
        self.ClockBegin2 = int(1425)
        self.ClockEnd2 = int(1e9)

        self.EnergyModel0 = xgb.XGBRegressor()
        self.EnergyModel1 = xgb.XGBRegressor()
        self.EnergyModel2 = xgb.XGBRegressor()

        self.TimeModel0 = xgb.XGBRegressor()
        self.TimeModel1 = xgb.XGBRegressor()
        self.TimeModel2 = xgb.XGBRegressor()

    def Init(self, XGBModelFolderDir, GPUName):
        
        # tmpDir = os.path.join(XGBModelFolderDir, "EnergyModel0.json")
        # print("EP_OPT_XGBOOST.Init: tmpDir = {}".format(tmpDir))
        self.EnergyModel0.load_model(os.path.join(XGBModelFolderDir, "EnergyModel0-"+GPUName+".json"))
        self.EnergyModel1.load_model(os.path.join(XGBModelFolderDir, "EnergyModel1-"+GPUName+".json"))
        self.EnergyModel2.load_model(os.path.join(XGBModelFolderDir, "EnergyModel2-"+GPUName+".json"))

        self.TimeModel0.load_model(os.path.join(XGBModelFolderDir, "TimeModel0-"+GPUName+".json"))
        self.TimeModel1.load_model(os.path.join(XGBModelFolderDir, "TimeModel1-"+GPUName+".json"))
        self.TimeModel2.load_model(os.path.join(XGBModelFolderDir, "TimeModel2-"+GPUName+".json"))

        return

    def Predict(self, dictFeature, arrayClock, ClockBase):

        # print("dictFeature: \n{}".format(dictFeature))
        # print("arrayClock: \n{}".format(arrayClock))
        # print("ClockBase = {}".format(ClockBase))

        tmpTime = dictFeature["Time"]
        del dictFeature["Energy"]
        del dictFeature["Time"]
        
        # wfr 20210818 modify 0 value
        if "sm__inst_executed.sum.per_second" in dictFeature.keys() and dictFeature["sm__inst_executed.sum.per_second"] < 1e-9:
            dictFeature["sm__inst_executed.sum.per_second"] = 1e3
        if "sm__inst_executed.sum" in dictFeature.keys() and dictFeature["sm__inst_executed.sum"] < 1e-9:
            dictFeature["sm__inst_executed.sum"] = dictFeature["sm__inst_executed.sum.per_second"] * tmpTime
        if "l1tex__t_sectors_lookup_miss.sum" in dictFeature.keys() and dictFeature["l1tex__t_sectors_lookup_miss.sum"] + dictFeature["l1tex__t_sectors_lookup_hit.sum"] < 1e-9:
            dictFeature["l1tex__t_sectors_lookup_hit.sum"] = 1
        if "lts__t_sectors_lookup_miss.sum" in dictFeature.keys() and dictFeature["lts__t_sectors_lookup_miss.sum"] + dictFeature["lts__t_sectors_lookup_hit.sum"] < 1e-9:
            dictFeature["lts__t_sectors_lookup_hit.sum"] = 1

        tmpDict = {}
        tmpDict["IPCPct"] = 0.0
        tmpDict["L1MissPerInst"] = 0.0
        tmpDict["L1MissPct"] = 0.0
        tmpDict["L2MissPerInst"] = 0.0
        tmpDict["L2MissPct"] = 0.0
        tmpDict["SMActCycPct"] = 0.0
        dictMetric = {**tmpDict, **dictFeature}

        IPCPercentSacle = 1.2
        CacheMissPerInstSacle = 2.5 * 100  # CacheMissPerInst 的调节系数
        # 10 * 10

        IPCPercent = dictMetric["sm__inst_executed.sum.pct_of_peak_sustained_active"] * IPCPercentSacle
        if np.abs(IPCPercent) < 1e-12:
            L1CacheMissPerInst = 0.0
            L1MissPct = 0.0
            L2CacheMissPerInst = 0.0
            L2MissPct = 0.0
        else:
            L1CacheMissPerInst = dictMetric["l1tex__t_sectors_lookup_miss.sum"] / dictMetric["sm__inst_executed.sum"] * CacheMissPerInstSacle  # 乘调节系数
            L2CacheMissPerInst = dictMetric["lts__t_sectors_lookup_miss.sum"] / dictMetric["sm__inst_executed.sum"] * CacheMissPerInstSacle  # 乘调节系数
            if (dictMetric["l1tex__t_sectors_lookup_miss.sum"] + dictMetric["l1tex__t_sectors_lookup_hit.sum"]) < 1e-15:
                L1MissPct = 0.0
            else:
                L1MissPct = dictMetric["l1tex__t_sectors_lookup_miss.sum"] / (dictMetric["l1tex__t_sectors_lookup_miss.sum"] + dictMetric["l1tex__t_sectors_lookup_hit.sum"])
            if (dictMetric["lts__t_sectors_lookup_miss.sum"] + dictMetric["lts__t_sectors_lookup_hit.sum"]) < 1e-15:
                L2MissPct = 0.0
            else:
                L2MissPct = dictMetric["lts__t_sectors_lookup_miss.sum"] / (dictMetric["lts__t_sectors_lookup_miss.sum"] + dictMetric["lts__t_sectors_lookup_hit.sum"])

        if np.abs(dictMetric["gpu__cycles_active.avg"]) < 1e-12:
            SMActiveCyclePercent = 0
        else:
            SMActiveCyclePercent = dictMetric["sm__cycles_active.avg"] / dictMetric["gpu__cycles_active.avg"] * 100

        if IPCPercent >= 100:
            # print("IPCPercent = {:.2f}".format(IPCPercent))
            IPCPercent = 99.99
            # print("Set IPCPercent = 99.99")
        if L1CacheMissPerInst >= 100:
            # print("L1CacheMissPerInst = {:.2f}".format(L1CacheMissPerInst))
            L1CacheMissPerInst = 99.99
            # print("Set L1CacheMissPerInst = 99.99")
        if L2CacheMissPerInst >= 100:
            # print("L2CacheMissPerInst = {:.2f}".format(L2CacheMissPerInst))
            L2CacheMissPerInst = 99.99
            # print("Set L2CacheMissPerInst = 99.99")
        if SMActiveCyclePercent >= 100:
            # print("SMActiveCyclePercent = {:.2f}".format(SMActiveCyclePercent))
            SMActiveCyclePercent = 99.99
            # print("Set SMActiveCyclePercent = 99.99")

        IPCPercent = IPCPercent # / 100
        L1CacheMissPerInst = L1CacheMissPerInst # / 100
        L2CacheMissPerInst = L2CacheMissPerInst # / 100
        SMActiveCyclePercent = SMActiveCyclePercent # / 100

        dictMetric["IPCPct"] = IPCPercent
        dictMetric["L1MissPerInst"] = L1CacheMissPerInst
        dictMetric["L1MissPct"] = L1MissPct
        dictMetric["L2MissPerInst"] = L2CacheMissPerInst
        dictMetric["L2MissPct"] = L2MissPct
        dictMetric["SMActCycPct"] = SMActiveCyclePercent

        del dictMetric["sm__inst_executed.sum"]
        del dictMetric["sm__inst_executed.sum.per_second"]
        del dictMetric["sm__cycles_active.avg"]
        del dictMetric["gpu__cycles_active.avg"]
        del dictMetric["l1tex__t_sectors_lookup_hit.sum"]
        del dictMetric["l1tex__t_sectors_lookup_miss.sum"]
        del dictMetric["lts__t_sectors_lookup_hit.sum"]
        del dictMetric["lts__t_sectors_lookup_miss.sum"]
        # del dictMetric["sm__inst_executed_pipe_lsu.sum"]
        # del dictMetric["sm__inst_executed_pipe_alu.sum"]
        # del dictMetric["sm__inst_executed_pipe_adu.sum"]
        # del dictMetric["sm__inst_executed_pipe_fma.sum"]
        # del dictMetric["sm__inst_executed_pipe_fp16.sum"]
        # del dictMetric["sm__inst_executed_pipe_fp64.sum"]
        # del dictMetric["sm__inst_executed_pipe_cbu.sum"]
        # del dictMetric["sm__inst_executed_pipe_tex.sum"]
        # del dictMetric["sm__inst_executed_pipe_uniform.sum"]
        # del dictMetric["sm__inst_executed_pipe_xu.sum"]
        # del dictMetric["sm__inst_executed_pipe_tensor.sum"]
        # del dictMetric["sm__inst_executed_pipe_ipa.sum"]
        # del dictMetric["sm__inst_executed_pipe_ipa.sum.pct_of_peak_sustained_active"]

        print("dictMetric:")
        print(dictMetric)

        # wfr construct feature matrix
        arrayMetric = np.array(list(dictMetric.values()))
        arrayFeature = np.tile(arrayMetric, (len(arrayClock),1))
        arrayRelativeClock = (arrayClock / ClockBase).reshape(-1, 1)
        arrayFeature = np.concatenate((arrayRelativeClock, arrayFeature), axis=1)

        # wfr 20210522 devide Feature into 3 groups by arrayClock
        arrayIndex0 = np.argwhere((self.ClockBegin0 <= arrayClock) & (arrayClock <= self.ClockEnd0)).flatten()
        # print("arrayIndex0 = {}".format(arrayIndex0))
        arrayFeature0 = arrayFeature[arrayIndex0]
        arrayIndex1 = np.argwhere((self.ClockBegin1 <= arrayClock) & (arrayClock <= self.ClockEnd1)).flatten()
        # print("arrayIndex1 = {}".format(arrayIndex1))
        arrayFeature1 = arrayFeature[arrayIndex1]
        arrayIndex2 = np.argwhere((self.ClockBegin2 <= arrayClock) & (arrayClock <= self.ClockEnd2)).flatten()
        # print("arrayIndex2 = {}".format(arrayIndex2))
        arrayFeature2 = arrayFeature[arrayIndex2]

        # print("arrayFeature0.shape = {}".format(arrayFeature0.shape))
        # print("arrayFeature1.shape = {}".format(arrayFeature1.shape))
        # print("arrayFeature2.shape = {}".format(arrayFeature2.shape))

        # wfr 20210628 predict relative energy
        PredictedEnergy0 = self.EnergyModel0.predict(arrayFeature0)
        PredictedEnergy1 = self.EnergyModel1.predict(arrayFeature1)
        PredictedEnergy2 = self.EnergyModel2.predict(arrayFeature2)


        # wfr 20210628 predict relative time
        PredictedTime0 = self.TimeModel0.predict(arrayFeature0)
        PredictedTime1 = self.TimeModel1.predict(arrayFeature1)
        PredictedTime2 = self.TimeModel2.predict(arrayFeature2)


        # wfr 20210628 reorder according to arrayClock
        PredictedEnergy = np.zeros(len(arrayClock))
        PredictedEnergy[arrayIndex0] = PredictedEnergy0
        PredictedEnergy[arrayIndex1] = PredictedEnergy1
        PredictedEnergy[arrayIndex2] = PredictedEnergy2


        PredictedTime = np.zeros(len(arrayClock))
        PredictedTime[arrayIndex0] = PredictedTime0
        PredictedTime[arrayIndex1] = PredictedTime1
        PredictedTime[arrayIndex2] = PredictedTime2


        # PredictedEDP = PredictedEnergy * PredictedTime
        # PredictedED2P = PredictedEDP * PredictedTime

        return PredictedEnergy, PredictedTime

