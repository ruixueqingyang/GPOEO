# -*- coding: utf-8 -*-
from scipy.fftpack import fft, fftshift, ifft
from scipy.fftpack import fftfreq
from scipy.signal import find_peaks
from scipy import signal
import numpy as np
import matplotlib.pyplot as plt
import pickle
import warnings
import sys

from scipy.signal.filter_design import maxflat
warnings.filterwarnings("ignore")

MAPEMax = 1e4
MAPEStdMax = 1e4
FigCount = 0
TLowBoundBase = 2.5
TLowBound = TLowBoundBase
TRound = 6
SetTLowBound = False
GrpFigCount = 0

# 计算最小公倍数
def lcm(x, y):
    m = max(x, y)
    n = min(x, y)
    while m%n:
        m, n = n, m%n
    return x*y//n

# wfr 20210107 求一组短周期的近似公倍数周期
def ApproximateLCM(arrayFactor, minALCM):
    arrayALCM = np.array([])
    if np.round(minALCM/np.max(arrayFactor)) - minALCM/np.max(arrayFactor) < 0:
        ALCM = np.max(arrayFactor) * np.round(minALCM / np.max(arrayFactor))
    else:
        ALCM = minALCM

    # tmpALCM = minALCM
    # maxErr = 1.0 # 最大百分比误差

    while True:
        arrayTmp = ALCM / arrayFactor
        arrayInteger = np.round(arrayTmp) # 最接近的周期整数倍
        arrayDecimal = np.abs(arrayTmp - arrayInteger) # 与最接近的周期整数倍, 相差的周期百分比
        arrayErr = arrayDecimal / arrayInteger
        maxErr = np.max(arrayErr)
        if maxErr < 0.1:
            if len(arrayALCM) > 0:
                # 给出几个备选, 但也不能太多, 因为1倍周期和2倍周期无法区分, 因此备选不能接近2倍周期
                if (ALCM / arrayALCM[0] > 1.3) \
                    or (len(arrayALCM) >= len(arrayFactor)) \
                    or (arrayALCM[-1]-arrayALCM[0] > 0.6 * np.max(arrayFactor)):
                    break
            arrayALCM = np.append(arrayALCM, ALCM)
        ALCM += 0.2 * np.max(arrayFactor)

    return arrayALCM

# wfr 20210130 先计算 N 位点, 在找出其中 附近采样点分布最密集的 N 位点
# PctRange 用来表征密集程度, 表示要求有 PctRange比例 的 采样点 在 N 位点附近
def FindClusterCenter(arrayP, N, PctRange):
    arrayTmpIndex = np.argsort(arrayP) # 将 arrayP 升序排列得到的 索引
    PointCount = N - 1  # wfr 20210127 计算 N 位点
    arrayPoint = np.linspace(0, 1, PointCount + 2)[1:-1]
    arrayPoint = np.floor(arrayPoint * len(arrayP))
    arrayPoint = arrayP[arrayTmpIndex[arrayPoint.astype(int)]]
    arrayHalfRange = np.ones(PointCount) * (arrayP[arrayTmpIndex[-1]] - arrayP[arrayTmpIndex[0]])

    # wfr 20210130 定义 N 位点的 附近 的范围, 0.3 表示 附近点的数量是采样点总数的 30%
    # 就是要找到满足该百分比的 对称区间 的范围
    # PctRange = 0.3
    SampleCount = len(arrayP)
    for i in range(PointCount):
        # 初始化区间半宽度上下限
        HalfRangeMin = 0
        HalfRangeMax = np.max([ arrayP[arrayTmpIndex[-1]] - arrayPoint[i], arrayPoint[i] - arrayP[arrayTmpIndex[0]] ])
        # 半宽度范围小于一定阈值则不再循环
        while HalfRangeMax - HalfRangeMin > 0.03 * (arrayP[arrayTmpIndex[-1]] - arrayP[arrayTmpIndex[0]]):
            # 二分搜索, 尝试半宽度范围的中点
            HalfRange = (HalfRangeMin + HalfRangeMax) / 2
            # 计算范围内采样点数量
            SampleCountIn = np.sum( ((arrayPoint[i]-HalfRange) < arrayP) & (arrayP < (arrayPoint[i]+HalfRange)) )
            # 更新半宽度范围
            if SampleCountIn / SampleCount < PctRange:
                HalfRangeMin = HalfRange
            elif SampleCountIn / SampleCount >= PctRange:
                HalfRangeMax = HalfRange

        arrayHalfRange[i] = HalfRange

    arrayRangeIndex = np.argsort(arrayHalfRange)

    # wfr 20210130 返回附近采样点最密集的 N 位点 及 达到 PctRange 的 最小区间半宽度
    return arrayPoint[arrayRangeIndex[0]], arrayHalfRange[arrayRangeIndex[0]]

# wfr 20210126 聚类, 合并区间, 不至于有太多的区间
def GrpClustering(arrayP):
    Mean = np.mean(arrayP)

    # wfr 20210130 从 N 位点中挑选聚类的初始中心点, 从其中挑选附近采样点最密集的 N 位点
    Point, Diff = FindClusterCenter(arrayP, 5, 0.33)
    tmpLow = Point - Diff
    tmpUp = Point + Diff

    arrayIndexIn = np.argwhere((tmpLow <= arrayP) & (arrayP <= tmpUp))  # 在中位数附近邻域的点的 index
    arrayIndexIn = arrayIndexIn[:, 0]
    if len(arrayIndexIn) < 1:
        print("DistributionMAPE: ERROR: 在中位数邻域没找到采样点")
    elif len(arrayIndexIn) > 1:
        arrayTmp = (arrayIndexIn[1:] - arrayIndexIn[:(-1)]) > 1  # 后一个 indx 减 前一个 index 大于 1, 说明不连续, 是区间分界
        arrayBeginFlag = np.insert(arrayTmp, 0, True)  # 区间开始点的 flag 是 true
        arrayEndFlag = np.append(arrayTmp, True)  # 区间结束点(包含)的 flag 是 true
        arrayIndexBegin = arrayIndexIn[arrayBeginFlag]  # 区间开始点的 index
        arrayIndexEnd = arrayIndexIn[arrayEndFlag] + 1  # 区间结束点(不包含)的 index
    else:
        arrayIndexBegin = arrayIndexIn
        arrayIndexEnd = arrayIndexIn + 1

    arrayIndexBeginOrigin = arrayIndexBegin
    arrayIndexEndOrigin = arrayIndexEnd

    # 一共有 len(arrayIndexBegin)+1 个空隙需要尝试合并(包括首尾两边的空隙)
    arrayIsolateFlag = np.zeros(len(arrayIndexBegin)).astype(bool)  # 用来表示对应区间是否尝试过进行合并
    stdP = np.std(arrayP) * 0.999  # 防止相等时的不确定情况
    # wfr 20210202 修改误差种数
    # MeanErrorShort = 0.04 # 待被合并的 区间 的 平均值的误差
    MeanErrorGap = 0.04 # 待被合并的 间隙 的 平均值的误差
    MeanErrorGrp = 0.03  # 合并后区间 的 平均值的误差
    ShortGrpPct = 0.04 # 极小区间阈值, 小于阈值的区间将使用更大的误差
    ScaleFactor = 2 # 误差增大系数

    arrayIsolateIndex = np.argsort(-1 * (arrayIndexEnd - arrayIndexBegin))
    i = arrayIsolateIndex[0]
    while 0 <= i and i <= len(arrayIndexBegin) - 1:

        meanGrp = np.mean(arrayP[arrayIndexBegin[i]: arrayIndexEnd[i]])

        isMerged = True
        while isMerged == True:
            isMerged = False

            # wfr 20210127 尝试合并左侧
            if i == 0:
                if arrayIndexBegin[0] != 0:  # 尝试合并最左侧空隙
                    tmpStd = np.std(arrayP[0: arrayIndexEnd[0]])
                    tmpMean = np.mean(arrayP[0: arrayIndexEnd[0]])
                    tmpMeanGap = np.mean(arrayP[0: arrayIndexBegin[0]])

                    # wfr 20210202 判断 gap 是否极短, 若是则增大误差
                    if arrayIndexBegin[0] <= ShortGrpPct * len(arrayP):
                        tmpMeanErrorGap = ScaleFactor * MeanErrorGap
                    else:
                        tmpMeanErrorGap = MeanErrorGap
                    # wfr 20210202 判断 区间 是否极短, 若是则增大误差
                    if arrayIndexEnd[0] <= ShortGrpPct * len(arrayP):
                        tmpMeanErrorGrp = ScaleFactor * MeanErrorGrp
                        tmpStdP = ScaleFactor * stdP
                    else:
                        tmpMeanErrorGrp = MeanErrorGrp
                        tmpStdP = stdP

                    if tmpStd < tmpStdP and np.abs((meanGrp - tmpMean) / np.mean([meanGrp, tmpMean])) < tmpMeanErrorGrp \
                        and np.abs((meanGrp - tmpMeanGap) / np.mean([meanGrp, tmpMeanGap])) < tmpMeanErrorGap:
                        # 合并成功
                        arrayIndexBegin[0] = 0
                        meanGrp = tmpMean
                        isMerged = True
            elif True or arrayIsolateFlag[i-1] == False:  # 尝试合并最左侧的 区间 和 空隙
                tmpStd = np.std(arrayP[arrayIndexBegin[i - 1]: arrayIndexEnd[i]])
                tmpMean = np.mean(arrayP[arrayIndexBegin[i - 1]: arrayIndexEnd[i]])
                # tmpMeanPrev = np.mean(arrayP[arrayIndexBegin[i - 1]: arrayIndexBegin[i]])
                tmpMeanGap = np.mean(arrayP[arrayIndexEnd[i - 1]: arrayIndexBegin[i]])

                # wfr 20210202 判断 gap 是否极短, 若是则增大误差
                if arrayIndexBegin[i] - arrayIndexEnd[i-1] <= ShortGrpPct * len(arrayP):
                    tmpMeanErrorGap = ScaleFactor * MeanErrorGap
                else:
                    tmpMeanErrorGap = MeanErrorGap
                # wfr 20210202 判断 区间 是否极短, 若是则增大误差
                if arrayIndexEnd[i] - arrayIndexBegin[i-1] <= ShortGrpPct * len(arrayP):
                    tmpMeanErrorGrp = ScaleFactor * MeanErrorGrp
                    tmpStdP = ScaleFactor * stdP
                else:
                    tmpMeanErrorGrp = MeanErrorGrp
                    tmpStdP = stdP

                if tmpStd < tmpStdP and np.abs((meanGrp - tmpMean) / np.mean([meanGrp, tmpMean])) < tmpMeanErrorGrp \
                    and np.abs((meanGrp - tmpMeanGap) / np.mean([meanGrp, tmpMeanGap])) < tmpMeanErrorGap:
                    # and np.abs((meanGrp - tmpMeanPrev) / np.mean([meanGrp, tmpMeanPrev])) < tmpMeanError1:
                    # 合并成功
                    arrayIndexBegin = np.delete(arrayIndexBegin, i)
                    arrayIndexEnd = np.delete(arrayIndexEnd, i - 1)
                    arrayIsolateFlag = np.delete(arrayIsolateFlag, i - 1)
                    meanGrp = tmpMean
                    isMerged = True
                    i -= 1

            # wfr 20210127 尝试合并右侧
            if i == len(arrayIndexBegin) - 1:
                if arrayIndexEnd[-1] != len(arrayP):  # 尝试合并最右侧空隙
                    tmpStd = np.std(arrayP[arrayIndexBegin[i]:])
                    tmpMean = np.mean(arrayP[arrayIndexBegin[i]:])
                    tmpMeanGap = np.mean(arrayP[arrayIndexEnd[i]:])

                    # wfr 20210202 判断 gap 是否极短, 若是则增大误差
                    if len(arrayP) - arrayIndexEnd[i] <= ShortGrpPct * len(arrayP):
                        tmpMeanErrorGap = ScaleFactor * MeanErrorGap
                    else:
                        tmpMeanErrorGap = MeanErrorGap
                    # wfr 20210202 判断 区间 是否极短, 若是则增大误差
                    if len(arrayP) - arrayIndexBegin[i] <= ShortGrpPct * len(arrayP):
                        tmpMeanErrorGrp = ScaleFactor * MeanErrorGrp
                        tmpStdP = ScaleFactor * stdP
                    else:
                        tmpMeanErrorGrp = MeanErrorGrp
                        tmpStdP = stdP

                    if tmpStd < tmpStdP and np.abs((meanGrp - tmpMean) / np.mean([meanGrp, tmpMean])) < tmpMeanErrorGrp \
                        and np.abs((meanGrp - tmpMeanGap) / np.mean([meanGrp, tmpMeanGap])) < tmpMeanErrorGap:
                        # 合并成功
                        arrayIndexEnd[-1] = len(arrayP)
                        meanGrp = tmpMean
                        isMerged = True
            elif True or arrayIsolateFlag[i+1] == False:  # 尝试合并最右侧的 区间 和 空隙
                tmpStd = np.std(arrayP[arrayIndexBegin[i]: arrayIndexEnd[i + 1]])
                tmpMean = np.mean(arrayP[arrayIndexBegin[i]: arrayIndexEnd[i + 1]])
                tmpMeanGap = np.mean(arrayP[arrayIndexEnd[i]: arrayIndexBegin[i + 1]])
                # tmpMeanBack = np.mean(arrayP[arrayIndexEnd[i]: arrayIndexEnd[i + 1]])

                # wfr 20210202 判断 gap 是否极短, 若是则增大误差
                if arrayIndexBegin[i+1] - arrayIndexEnd[i] <= ShortGrpPct * len(arrayP):
                    tmpMeanErrorGap = ScaleFactor * MeanErrorGap
                else:
                    tmpMeanErrorGap = MeanErrorGap
                # wfr 20210202 判断 区间 是否极短, 若是则增大误差
                if arrayIndexEnd[i+1] - arrayIndexBegin[i] <= ShortGrpPct * len(arrayP):
                    tmpMeanErrorGrp = ScaleFactor * MeanErrorGrp
                    tmpStdP = ScaleFactor * stdP
                else:
                    tmpMeanErrorGrp = MeanErrorGrp
                    tmpStdP = stdP

                if tmpStd < tmpStdP and np.abs((meanGrp - tmpMean) / np.mean([meanGrp, tmpMean])) < tmpMeanErrorGrp \
                    and np.abs((meanGrp - tmpMeanGap) / np.mean([meanGrp, tmpMeanGap])) < tmpMeanErrorGap:
                    # and np.abs((meanGrp - tmpMeanBack) / np.mean([meanGrp, tmpMeanBack])) < tmpMeanErrorGap \
                    # 合并成功
                    arrayIndexBegin = np.delete(arrayIndexBegin, i + 1)
                    arrayIndexEnd = np.delete(arrayIndexEnd, i)
                    arrayIsolateFlag = np.delete(arrayIsolateFlag, i + 1)
                    meanGrp = tmpMean
                    isMerged = True

        # wfr 20210127 标记 i 为已经尝试过, 找到下一个没尝试过的长度最长的 区间
        arrayIsolateFlag[i] = True
        i = -1
        arrayIsolateIndex = np.argsort(-1 * (arrayIndexEnd - arrayIndexBegin))
        if len(arrayIsolateIndex) > 0:
            tmp = np.argwhere(arrayIsolateFlag[arrayIsolateIndex] == False)
            tmp = tmp[:, 0]
            if len(tmp) > 0:
                i = arrayIsolateIndex[tmp[0]]

    # wfr 20210202 评估聚类结果, 如果有一个长度接近整个周期的区间, 则认为是不应该聚类, 因为聚类后会导致误差异常减小
    arrayInterval = arrayIndexEnd - arrayIndexBegin
    for i in range(len(arrayInterval)):
        if arrayInterval[i] / len(arrayP) > 0.85:
            tmp0 = arrayIndexBegin[i] <= arrayIndexBeginOrigin
            tmp1 = arrayIndexEndOrigin <= arrayIndexEnd[i]
            tmp = np.argwhere(tmp0 & tmp1)[:, 0]
            arrayIndexBegin = np.delete(arrayIndexBegin, i)
            arrayIndexBegin = np.insert(arrayIndexBegin, i, arrayIndexBeginOrigin[tmp])
            arrayIndexEnd = np.delete(arrayIndexEnd, i)
            arrayIndexEnd = np.insert(arrayIndexEnd, i, arrayIndexEndOrigin[tmp])
            break

    # 开始点/结束点 index 交叉存放, 形成区间分界 index 序列
    arrayGroupIndex = np.zeros(2 * len(arrayIndexBegin)).astype(int)
    arrayGroupIndex[2 * np.arange(0, len(arrayIndexBegin))] = arrayIndexBegin
    arrayGroupIndex[1 + 2 * np.arange(0, len(arrayIndexBegin))] = arrayIndexEnd
    # 补充 0 和 len(arrayP), 如果缺的话
    if arrayGroupIndex[0] != 0:
        arrayGroupIndex = np.insert(arrayGroupIndex, 0, 0)
    if arrayGroupIndex[-1] != len(arrayP):
        arrayGroupIndex = np.append(arrayGroupIndex, len(arrayP))

    # fig = plt.figure(figsize=(8, 4))  # 定义一个图像窗口
    # ax = fig.add_subplot(111)
    # ax.plot(arrayP)
    # for v in arrayGroupIndex:
    #     ax.axvline(x=v, color="black", linestyle="--", linewidth=0.5)  # 横座标 v 画一条横线
    # plt.show()
    # plt.close(fig)

    return arrayGroupIndex

# 计算 周期为 T 时的功率分布情况的 MAPE(Mean Absolute Percentage Error)
# 功率波形采样序列 arraySample
# 采样时间序列 arrayTimeStamp
# 周期 T
# 该函数是执行热点, 且有优化空间, 可以更加向量化
# wfr 20210108 传入公倍数周期的最大因子
def DistributionMAPE(T, arraySample, arrayTimeStamp, algorithm = "mean", TRef = -1):

    global MAPEMax, MAPEStdMax
    TMAPE = MAPEMax
    TMAPEStd = MAPEStdMax
    if T > 0.5 * arrayTimeStamp[-1]: # or T < 2:
        return TMAPE, TMAPEStd # 排除 长度 大于 测量区间一半的 周期

    NumTRegion = int(arrayTimeStamp[-1] / T)  # 采样时间内包含多少个周期
    SampleInterval = arrayTimeStamp[1];  # 采样间隔
    NumSample = int(T / (SampleInterval))  # 一个周期中的采样点数量

    arrayTRegionMAPE = np.array([])
    arrayIndex = np.arange(0, (NumTRegion + 0.1), 1)  # 最后一个区间可能不是完整的, 所以不要最后一个
    arrayIndex = arrayIndex * NumSample
    arrayIndex = arrayIndex.astype(np.int)  # 每个 完整 周期区间的 开始和结束时间戳 的 index

    # tmpOffset = len(arraySample) - arrayIndex[-1]
    # arrayIndex += int(0.5 * tmpOffset)

    for indexTRgn in range( NumTRegion - 1 ): # 对于每两个相邻的周期区间, 衡量其功率数据分布相似情况

        # wfr 20210106
        arrayP0 = arraySample[ arrayIndex[indexTRgn] : arrayIndex[indexTRgn+1] ]
        arrayP1 = arraySample[ arrayIndex[indexTRgn+1] : arrayIndex[indexTRgn+2] ]

        tmpMean0 = np.mean(arrayP0)
        tmpMean1 = np.mean(arrayP1)
        tmpStd0 = np.std(arrayP0)
        tmpStd1 = np.std(arrayP1)

        if tmpStd0 < tmpStd1:
            arrayGroupIndex = GrpClustering(arrayP1)
        else:
            arrayGroupIndex = GrpClustering(arrayP0)

        # global GrpFigCount
        #
        # fig = plt.figure(figsize=(8, 4))  # 定义一个图像窗口
        # ax = fig.add_subplot(111)
        # ax.plot(arrayP0)
        # for v in arrayGroupIndex:
        #     ax.axvline(x=v, color="black", linestyle="--", linewidth=0.5)  # 横座标 v 画一条横线
        # plt.savefig("./Trace/Grp-" + str(GrpFigCount) + "-0.png")
        # # plt.show()
        # plt.close()
        #
        # fig = plt.figure(figsize=(8, 4))  # 定义一个图像窗口
        # ax = fig.add_subplot(111)
        # ax.plot(arrayP1)
        # for v in arrayGroupIndex:
        #     ax.axvline(x=v, color="black", linestyle="--", linewidth=0.5)  # 横座标 v 画一条横线
        # plt.savefig("./Trace/Grp-" + str(GrpFigCount) + "-1.png")
        # # plt.show()
        # plt.close(fig)
        #
        # GrpFigCount += 1

        # 先取出对应的分组后的数组
        NumGroup = len(arrayGroupIndex)-1
        arrayGrouped0 = np.zeros( NumGroup )
        arrayGrouped1 = np.zeros( NumGroup )
        # 两个相邻周期区间分别分成 NumGroup 组, 计算每组中 功率与区间平均功率的差 的平均值
        for indexGrp in range(NumGroup):
            # wfr 20210106
            tmpArray0 = arraySample[ arrayIndex[indexTRgn]+arrayGroupIndex[indexGrp]: arrayIndex[indexTRgn]+arrayGroupIndex[indexGrp+1] ]
            tmpArray1 = arraySample[ arrayIndex[indexTRgn+1]+arrayGroupIndex[indexGrp]: arrayIndex[indexTRgn+1]+arrayGroupIndex[indexGrp+1] ]

            arrayGrouped0[indexGrp] = np.mean(tmpArray0) - tmpMean0
            arrayGrouped1[indexGrp] = np.mean(tmpArray1) - tmpMean1

        # 两个相邻周期区间的 对应组 分别两两 求 SMAPE
        arrayGroupMAPE = np.abs((arrayGrouped1 - arrayGrouped0) / np.mean([tmpMean0, tmpMean1]) * 100)

        if algorithm != "mean":
            # 临近搜索时, 不用均值, 而用最值, 这样才更能体现出波形的非周期性
            TRegionMAPE = np.max( arrayGroupMAPE )
        else:
            # wfr 这里改成根据区间采样点数量加权平均
            arrayWeight = arrayGroupIndex[1:] - arrayGroupIndex[:-1]
            TRegionMAPE = np.average(arrayGroupMAPE, weights=arrayWeight)
            # TRegionMAPE = np.mean( arrayGroupMAPE )
        arrayTRegionMAPE = np.append(arrayTRegionMAPE, TRegionMAPE)
    # end

    # wfr 20210828 对于 小备选周期, 划分的区间比较多, 很可能有误差非常小的区间, 不应该考虑这些区间, 因为可能处于一个大周期的平台上,
    # 因此考虑将 arrayTRegionMAPE 分成 TRef/T 组, 取出每组中的最大误差 重新组成 tmpArray
    if TRef < 0 or TRef / T < 1.7:
        TMAPE = np.mean(arrayTRegionMAPE)
        TMAPEStd = np.std(arrayTRegionMAPE)
    else:
        pass
        tmpEachCount = int(np.ceil(TRef / T)) # 每组中的区间个数
        tmpGrpCount = int(np.ceil(len(arrayTRegionMAPE) / tmpEachCount)) # 组数
        tmpAppendCount = int(tmpGrpCount * tmpEachCount - len(arrayTRegionMAPE)) # 需要填充的元素个数
        tmpArray = np.append(arrayTRegionMAPE, np.zeros(tmpAppendCount)) # 为了 rashape 而填充 0.0 元素
        tmpArray = tmpArray.reshape(tmpGrpCount, -1) # reshape 完成分组 [0,1,2], [3,4,5], ...
        tmpArray = np.max(tmpArray, axis=1).flatten() # 每组分别求最大值
        TMAPE = np.mean(tmpArray)
        TMAPEStd = np.std(tmpArray)

    return TMAPE, TMAPEStd

# wfr 20210116 这里使用新方法判断是否是无周期
def TCompute(arraySample, SampleInterval, TUpBound, isPlot = False, lastT=0.0, preference=0, TCandidateExtra=np.array([])):

    global MAPEMax, MAPEStdMax, TLowBoundBase, TLowBound, SetTLowBound

    fs = 1/(SampleInterval/1000)
    t = (SampleInterval/1000) * np.arange(0, len(arraySample), 1)
    # wfr 20210109 fft 算法采样倍率, 提高该值可以增大最大可以识别的周期, 提高频率/周期的分辨率
    # 频率分辨率是不变的, 周期分辨率是变化的, 周期越大分辨率越低
    FFTSampleRatio = 1

    # wfr 20210109 动态调节 fft算法 采样点数量, 即 FFTSampleRatio
    # 若 fft变换 分析出的 周期 接近 能分辨的最大周期, 则 增大 FFTSampleRatio, 再重新 分析
    for i in range(2):

        num_fft = FFTSampleRatio * t.size

        # 傅里叶变换
        idx = fftfreq(num_fft, 1/fs)
        arrayX = idx[:num_fft//2]
        arrayY = fft(arraySample, num_fft)
        arrayY = np.abs(arrayY)
        arrayY = arrayY[:num_fft//2]
        # arrayLogY = np.log10(arrayY[:num_fft//2])

        listPeakIndex, Properties = find_peaks( arrayY )

        # 取出峰值处的 频率 和 幅值
        arrayPeakX = arrayX[listPeakIndex]
        arrayPeak = arrayY[listPeakIndex]
        arrayPeakIndex = np.argsort(-1 * arrayPeak)  # 将 arrayPeak 降序排列得到的 索引
        # print("TCompute: len of arrayPeakX = {0}".format(len(arrayPeakX)))

        # print("arrayPeak = {0}".format(arrayPeak[arrayPeakIndex[:9]]))
        # print("Freq = {0}".format(arrayPeakX[arrayPeakIndex[:9]]))
        # print("T = {0}".format(1/arrayPeakX[arrayPeakIndex[:9]]))

        # 取出振幅最大的前几个周期, 且不大于周期上界
        arrayT = 1 / arrayPeakX[arrayPeakIndex]  # 先按照峰值大小 降序排列
        arrayPeakOrder = arrayPeak[arrayPeakIndex]
        # 先排除大于周期上限的周期
        tmpPeakOrder = arrayPeakOrder[(arrayT <= TUpBound)]
        arrayT = arrayT[(arrayT <= TUpBound)]
        # 再排除峰值不够大的周期
        arrayT = arrayT[(tmpPeakOrder > 0.65 * tmpPeakOrder[0])]
        if len(arrayT) == 0:
            print("TCompute ERROR: 没有备选周期!")
            return TUpBound, MAPEMax

        if i == 0:
            # wfr 20210109 计算 能分辨的次最大周期, 常数 3 代表次最大周期, 常数 2 代表最大周期
            TUpResolution = FFTSampleRatio * len(arraySample) / (0.5*fs) / 3
            if np.max(arrayT) > TUpResolution:
                FFTSampleRatio = np.ceil( TUpBound / len(arraySample) * (0.5*fs) * 3 )
            else:
                break

    # print("arrayT = {0}".format(arrayT))

    if isPlot == True:
        # plt.clf()
        # plt.ion()
        plt.figure(figsize=(14, 6))
        ax = plt.subplot(211)
        ax.set_title('original signal')
        plt.plot(t, arraySample)

        ax = plt.subplot(212)
        ax.set_title('fft transform')
        plt.plot(arrayX, 20 * np.log10(arrayY))
        ax.set_xlim(0, 2)
        # ax.set_xlim(0, 5)

        global FigCount
        import os
        WorkDir = "./tmp"
        FigFile = os.path.join(WorkDir, "TCompute" + str(FigCount) + ".png")
        plt.savefig(FigFile)
        FigCount += 1
        # plt.show()
        plt.close()

    if len(listPeakIndex) == 0:
        print("TCompute ERROR: 计算备选频率/周期出错")
        return TUpBound, MAPEMax

    # wfr 20210107 求近似最小公倍数周期, 以代替较小的(小于周期下限)周期
    arrayFactor = arrayT[ (arrayT < TLowBound) ]
    if len(arrayFactor) > 0:
        # wfr 20210108 公倍数周期的最大因子, 后续 MAPE计算 以及 邻近搜索 会用到
        FactorMax = np.max(arrayFactor) # wfr 20210107 小于阈值的备选周期 中的 最大值
        # print("FactorMax = {0}".format(FactorMax))
        arrayALCM = ApproximateLCM(arrayFactor, TLowBound)
        # print("ALCM = {0}".format(arrayALCM))
        arrayScaleT = np.delete(arrayT, np.argwhere(arrayT < TLowBound).flatten()) # wfr 20210107 删除小于阈值的备选周期
        # arrayScaleT = np.append(arrayScaleT, arrayFactor[0])
        # arrayScaleT = np.insert(arrayScaleT, 0, arrayFactor[0])
        # arrayScaleT = np.insert(arrayScaleT, 0, FactorMax) # wfr 20210107 保留 小于阈值的备选周期 中的 最大值
        arrayScaleT = np.append(arrayScaleT, FactorMax) # wfr 20210107 保留 小于阈值的备选周期 中的 最大值
        LenTNormal = len(arrayScaleT) # wfr 20210108 普通周期的数量
        arrayScaleT = np.append(arrayScaleT, arrayALCM)
    else:
        arrayScaleT = arrayT
        LenTNormal = len(arrayScaleT) # wfr 20210108 普通周期的数量
        FactorMax = 1e4

    arrayScaleT = np.append(arrayScaleT, TCandidateExtra)

    # print("arrayScaleT = {0}".format(arrayScaleT[:9]))

    if int(preference) == int(1):
        T_lower = lastT * 0.8
        T_upper = lastT * 1.5
    elif int(preference) == int(-1):
        T_lower = lastT * 0.66
        T_upper = lastT * 1.25
    if int(preference) != int(0):
        print("lastT = {:.2f}, set lowerT = {:.2f}, upperT = {:.2f}".format(lastT, T_lower, T_upper))
        print("arrayScaleT remove: [", end="")
        tmpArr = arrayScaleT.tolist()
        for cand_T in arrayScaleT:
            if cand_T < T_lower or cand_T > T_upper:
                print("{:.2f}, ".format(cand_T), end="")
                tmpArr.remove(cand_T)
        arrayScaleT = np.array(tmpArr)
        print("]")
        if len(arrayScaleT) <= int(0):
            print("arrayScaleT add: [", end="")
            for cand_T in np.arange(T_lower, T_upper, (T_upper-T_lower-1e-15)/4):
                print("{:.2f}, ".format(cand_T), end="")
                arrayScaleT = np.append(arrayScaleT, cand_T)
            print("]")
    else:
        pass
        print("==>no preference")
    sys.stdout.flush()

    arrayTMAPE = MAPEMax * np.ones(len(arrayScaleT))
    arrayTMAPEStd = MAPEStdMax * np.ones(len(arrayScaleT))

    for i in range( len(arrayScaleT) ): # 对于每个猜测的周期长度
        arrayTMAPE[i], arrayTMAPEStd[i] = DistributionMAPE(arrayScaleT[i], arraySample, t, "mean", np.max(arrayScaleT))

    # 如果峰值最高的周期的 MAPE 没有被计算, 即测量时间不够长, 就直接返回不稳定
    if arrayTMAPE[0] > MAPEMax - 1 or int(2 * sum(arrayTMAPE > MAPEMax - 1)) >= int(len(arrayTMAPE)):
        print("TCompute: 本次测量时间不够长")
        print("TCompute: TOpt = {0:.2f} s".format(arrayScaleT[0]))
        print("TCompute: MAPEOpt = {0:.2f}".format(arrayTMAPE[0]))
        # return arrayScaleT[0], arrayTMAPE[0]
        return arrayScaleT[0], -1

    # wfr 20210129 修改根据 arrayTMAPE 和 arrayTMAPEStd 判断最优周期的规则
    # 先将 arrayTMAPEStdIndex 中的 0 都赋值成 其中的 非0最小值
    if np.sum(arrayTMAPEStd < 1e-6) == len(arrayTMAPEStd):
        arrayTMAPEStd[:] = 1
    elif np.sum(arrayTMAPEStd < 1e-6) > 0:
        arrayTMAPEStd[arrayTMAPEStd < 1e-6] = np.min(arrayTMAPEStd[arrayTMAPEStd > 1e-6])
    # arrayTError = arrayTMAPE * arrayTMAPEStd # 将两数组相乘, 用乘积来评价 周期 的误差
    arrayTIndex = np.argsort(arrayTMAPE) # 将 arrayTmp 升序排序 得到的 索引
    IndexOpt = arrayTIndex[0]

    # # print("arrayTMAPE = {0}".format(arrayTMAPE[:9]))
    # arrayTMAPEIndex = np.argsort(arrayTMAPE) # 将 arrayDistributionErrPct 升序排序 得到的 索引
    # arrayTMAPEStdIndex = np.argsort(arrayTMAPEStd) # 将 arrayTMAPEStdIndex 升序排序 得到的 索引
    #
    # # wfr 20210127 如果最小 MAPE 和 最小 MAPEStd 对应的 T 相同
    # if arrayTMAPEIndex[0] == arrayTMAPEStdIndex[0]:
    #     IndexOpt = arrayTMAPEIndex[0]
    # else: # wfr 20210127 如果最小 MAPE 和 最小 MAPEStd 对应的 T 不相同
    #     arrayPartIndex = np.argwhere(arrayTMAPE - arrayTMAPE[arrayTMAPEIndex[0]] < 0.08 * np.max(arrayScaleT))
    #     # arrayPartIndex = np.argwhere(arrayTMAPE < 1.5 * arrayTMAPE[arrayTMAPEIndex[0]])
    #     arrayPartIndex = arrayPartIndex[:,0]
    #     tmp = np.argsort(arrayTMAPEStd[arrayPartIndex])  # 将 arrayTMAPEStdIndex 升序排序 得到的 索引
    #     IndexOpt = arrayPartIndex[tmp[0]]

    # wfr 20210108 判断最优周期是 公倍数周期 还是 普通周期, 从而设置 公倍数周期的最大因子, 以支持后续 MAPE 计算
    TOpt = arrayScaleT[IndexOpt]
    MAPEOpt = arrayTMAPE[IndexOpt]
    MAPEStdOpt = arrayTMAPEStd[IndexOpt]
    np.set_printoptions(precision=2, suppress=True)
    print("TOpt = {0}".format(TOpt))
    print("arrayScaleT: {0}".format(arrayScaleT))
    # print("arrayTError: {0}".format(arrayTError))
    print("arrayTMAPE: {0}".format(arrayTMAPE))
    # print("arrayTMAPEStd: {0}".format(arrayTMAPEStd))

    # wfr 20210109 因为 fft变换 频率分辨率是不变的, 周期是频率的倒数, 其分辨率是变化的
    # 频率越低/周期越长, 周期分辨率越低, 所以需要动态调节邻近搜索区间
    # 频谱分析得到的周期可能有误差(因为周期分辨率的限制), 因此需要在此周期附近进行局部搜索, 得到更精确的周期
    # wfr 20210109 中心频率 及 频率刻度
    FreqCenter = 1 / TOpt
    FreqResolution = (0.5 * fs) / len(arraySample)
    # wfr 20210109 先计算频率邻近区间
    FreqLow = FreqCenter - 0.7 * FreqResolution
    FreqUp = FreqCenter + 0.7 * FreqResolution
    # wfr 20210109 再计算周期邻近区间
    TLow = 1 / FreqUp
    if FreqLow > 0:
        TUp = 1 / FreqLow
    else:
        TUp = 1.5 * TOpt
    # wfr 20210113 确保邻近搜索范围大于等于 +/-15%
    TLow = np.min([0.85 * TOpt, TLow])
    TUp = np.max([1.15 * TOpt, TUp])
    # wfr 20210109 用因子限制上下界, 防止对于公倍数周期过度搜索
    TLow = np.max([(TOpt-0.5*FactorMax), TLow])
    # TLow = np.max([TLowBound, TLow]) # wfr 20210121 搜索区间下限不小于 TUpBound
    TUp = np.min([(TOpt+0.5*FactorMax), TUp])
    # wfr 20210109 区间最多分8份
    TStep = (TUp - TLow) / 8
    TStep = np.min([TStep, 1]) # wfr 20210113 步长的上限是 1s
    TStep = np.max([TStep, 1 * SampleInterval/1000])
    # wfr 20210109 生成邻近搜索序列, 要包括区间端点
    arraySearchT = np.arange(TLow, TUp, TStep)
    arraySearchT = np.append(arraySearchT, TUp)
    arraySearchT = np.append(arraySearchT, TOpt)

    arraySearchTMAPE = MAPEMax * np.ones(len(arraySearchT))
    arraySearchTMAPEStd = MAPEStdMax * np.ones(len(arraySearchT))
    # 对于每个备选的周期, 计算 MAPE, MAPE越小越好, 越小说明功率变化/分布情况越一致
    for i in range( len(arraySearchT) ):
        arraySearchTMAPE[i], arraySearchTMAPEStd[i] = DistributionMAPE(arraySearchT[i], arraySample, t, "mean", np.max(arrayScaleT))

    arrayTIndex = np.argsort(arraySearchTMAPE)  # 将 arrayTmp 升序排序 得到的 索引
    IndexOpt = arrayTIndex[0]
    TOpt = arraySearchT[IndexOpt]
    MAPEOpt = arraySearchTMAPE[IndexOpt]

    # print("TCompute: arraySearchT: {0}".format(arraySearchT))
    # print("TCompute: arrayTError: {0}".format(arrayTError))
    # print("TCompute: arraySearchTMAPE: {0}".format(arraySearchTMAPE))
    # print("TCompute: arraySearchTMAPEStd: {0}".format(arraySearchTMAPEStd))

    # wfr 20210108 放大太短的周期
    if TOpt < TLowBound:
        # wfr 20210120 自适应调节周期下限, 保证不会相差一个周期, 或者相差一个周期, 但是仍然在 10% 以内
        # if SetTLowBound == False and TLowBound / TOpt > 6:
        #     TLowBound = np.ceil(10 * TOpt)
        #     SetTLowBound = True
        TOpt = TOpt * np.round(TLowBound / TOpt)

    # print("TCompute: TOpt = {0:.2f} s".format(TOpt))
    # print("TCompute: MAPEOpt = {0:.2f}".format(MAPEOpt))
    # print("")

    return TOpt, MAPEOpt

def NotPeriodic(arraySample, SampleInterval, T):
    TFixed = 8
    N = 4
    SigmaMax = 1
    SigmaPctMax = 0.04
    MeanErrMax = 0.04
    DiffErrMax = 0.20

    arraySample = arraySample[5:-5]
    # 采样时间过短 直接返回 False
    if (len(arraySample)-1) * (SampleInterval/1000) < N * TFixed:
        if T < TFixed:
            TFixed = T
        if (len(arraySample)-1) * (SampleInterval/1000) < N * TFixed:
            return False
    Step = int(TFixed / (SampleInterval / 1000))

    arrayRegion = np.array([])
    arrayMean = np.array([])
    arrayStd = np.array([])
    arrayDiffMax = np.array([])
    for i in range(N):
        begin = len(arraySample) - ((i+1) * Step)
        end = len(arraySample) - (i * Step)
        arrayTmp = np.array(arraySample[begin:end])
        arrayRegion = np.append(arrayRegion, arrayTmp)
        arrayMean = np.append(arrayMean, np.mean(arrayTmp))
        arrayStd = np.append(arrayStd, np.std(arrayTmp))
        arrayDiffMax = np.append(arrayDiffMax, np.max(np.abs( arrayTmp - arrayMean[i] )))

    # 如果相邻两区间平均功率相差过大则认为不是无周期
    for i in range(N-1):
        if np.abs(arrayMean[i]-arrayMean[i+1]) / (np.mean(arrayMean[i:i+1])) > MeanErrMax:
            return False

    # 如果 标准差 过大则认为不是无周期
    # if np.max(arrayStd) > SigmaMax:
    #     return False
    if np.max(arrayStd/arrayMean) > SigmaPctMax:
        return False

    # 如果 最大/最小值 超限则认为不是无周期
    if np.max(arrayDiffMax / arrayMean) > DiffErrMax:
        return False

    print("NotPeriodic: 无周期")
    return True


# wfr 20201230
def T_SpectrumAnalysis(listSample, SampleInterval, TUpBound, MeasureTFactor, TraceFileName, StrictMode="normal", lastT=-1, preference=0, isPlot = False):
    global MAPEMax, FigCount, TLowBoundBase, TLowBound, SetTLowBound
    FigCount = 0
    TLowBound = TLowBoundBase
    SetTLowBound = False

    # print("SpectrumAnalysis: 采样点数量 = {0}".format(len(listSample)))
    arraySample = np.array(listSample) # 去除刚开始的采样点, 因为可能异常偏低
    MeasureDuration = (len(arraySample)-1) * (SampleInterval/1000)

    arrayT = np.array([])
    arraySMAPE = np.array([])
    isStable = False
    MeasureDurationNext = -1

    # 保存原始数据到文件
    if len(TraceFileName) > 0:
        FileDir = "./Trace/"+TraceFileName+".pkl"
        pickle.dump(listSample, open(FileDir, "wb"))


    # 低通滤波
    # 采样频率 10Hz, 要滤除 Threshold Hz 以上的频率成分
    SampleFreq = 1/(SampleInterval/1000)
    Threshold = 2
    Wn = 2 * Threshold / SampleFreq
    b, a = signal.butter(8, Wn, 'lowpass')
    SampleFilted = signal.filtfilt(b, a, arraySample)
    # SampleFilted = SampleFilted[0:]


    tmpT, tmpSMAPE = TCompute(SampleFilted, SampleInterval, TUpBound, isPlot)
    # 如果测量时间不够长, 就直接返回不稳定
    if tmpT > (0.5 * MeasureDuration):
        T = tmpT
        isStable = False
        MeasureDurationNext = max(0.5 * tmpT, (MeasureTFactor * tmpT - MeasureDuration)) # 测量够 5倍 周期
        print("T_SpectrumAnalysis: 本次测量时间不够长")
        # if MeasureDuration > TUpBound and isStable == False:
        #     if True == NotPeriodic(arraySample, SampleInterval, T):
        #         if T < 4:
        #             T = np.ceil(4 / T) * T
        #         MeasureDurationNext = -1
        print("T_SpectrumAnalysis: TOpt = {0:.2f} s".format(tmpT))
        print("T_SpectrumAnalysis: isStable = {0}".format(isStable))
        print("T_SpectrumAnalysis: MeasureDurationNext = {0}".format(MeasureDurationNext))
        return T, isStable, MeasureDurationNext
    arrayT = np.append(arrayT, tmpT)
    arraySMAPE = np.append(arraySMAPE, tmpSMAPE)

    Step = 0.5
    MeasureDurationLeft = MeasureDuration - tmpT * Step
    while MeasureDurationLeft / np.max(arrayT) >= 2.8:
        # 计算剩余采样点的起始 index
        tmpIndexBegin = int( (MeasureDuration-MeasureDurationLeft) / (SampleInterval/1000) )
        arrayPart = SampleFilted[tmpIndexBegin:]
        tmpT, tmpSMAPE = TCompute(arrayPart, SampleInterval, TUpBound, isPlot, lastT, int(preference), arrayT)
        arrayT = np.append(arrayT, tmpT)
        arraySMAPE = np.append(arraySMAPE, tmpSMAPE)

        # 每次减去上次周期的长度
        MeasureDurationLeft = MeasureDurationLeft - tmpT * Step
        # MeasureDurationLeft = MeasureDurationLeft - np.mean(arrayT)
    print("T_SpectrumAnalysis: arrayT: {0}".format(arrayT))
    print("T_SpectrumAnalysis: arraySMAPE: {0}".format(arraySMAPE))


    # wfr 20210828 如果 测量区间长度 / 最好周期 < MeasureTFactor 则认为 测量时间不够长
    tmpIndex = np.argwhere(arraySMAPE < 0).flatten() # SMAPE < 0 说明 TCompute 认为测量时间不够长
    arraySMAPE[tmpIndex] = np.min(arraySMAPE)
    tmpIndex = np.argsort(arraySMAPE).flatten() # 将 tmpArraySMAPE 升序排列得到的 索引
    tmpT = np.max(arrayT[tmpIndex])
    if MeasureDuration / tmpT < MeasureTFactor:
        T = tmpT
        isStable = False
        print("T_SpectrumAnalysis: 本次测量时间不够长")
        MeasureDurationNext = max(0.5 * tmpT, (MeasureTFactor * tmpT - MeasureDuration)) # 测量够 5倍 周期
        # if MeasureDuration > TUpBound and isStable == False:
        #     if True == NotPeriodic(arraySample, SampleInterval, T):
        #         if T < 4:
        #             T = np.ceil(4 / T) * T
        #         MeasureDurationNext = -1
        print("T_SpectrumAnalysis: TOpt = {0:.2f} s".format(T))
        print("T_SpectrumAnalysis: isStable = {0}".format(isStable))
        print("T_SpectrumAnalysis: MeasureDurationNext = {0}".format(MeasureDurationNext))
        return T, isStable, MeasureDurationNext

    LenT = len(arrayT)
    LenMin = 3
    LenMax = 5
    if LenT < LenMin: # wfr 测量区间还比较短 
        tmpIndex = np.argsort(arraySMAPE) # 将 tmpArraySMAPE 升序排列得到的 索引
        T = arrayT[tmpIndex[0]]
        T = np.mean(arrayT[(0.65*T<arrayT)&(arrayT<1.35*T)])
        SMAPE = abs( (np.max(arrayT)-np.min(arrayT)) / np.mean(arrayT) )
        print("T_SpectrumAnalysis: SMAPE = {0:.2f}".format(SMAPE))

        isStable = False

        if MeasureDuration > 2.1 * TUpBound and SMAPE > 0.15:
            MeasureDurationNext = -1

        # 测量够 5倍 周期
        elif MeasureDuration < MeasureTFactor * np.max(arrayT):
            MeasureDurationNext = MeasureTFactor * np.max(arrayT) - MeasureDuration + 5
        else:
            MeasureDurationNext = np.ceil(MeasureDuration / np.max(arrayT)) * np.max(arrayT) - MeasureDuration + 5

    elif LenMin <= LenT:

        if StrictMode == "strict":
            tmpThreshold = 0.10
        elif StrictMode == "relaxed":
            tmpThreshold = 0.30
        else:
            tmpThreshold = 0.10

        tmp = min(LenT, LenMax)
        tmpIndexBegin = int(round(0.2 * LenT))
        tmpIndexEnd = int(round(0.8 * LenT)) - 1
        # tmpArrayT = np.array(arrayT[LenT-tmp:])
        # tmpArraySMAPE = np.array(arraySMAPE[LenT-tmp:])
        tmpArrayT = np.array(arrayT[tmpIndexBegin:tmpIndexEnd])
        tmpArraySMAPE = np.array(arraySMAPE[tmpIndexBegin:tmpIndexEnd])
        SMAPE = abs( (np.max(tmpArrayT)-np.min(tmpArrayT)) / np.mean(tmpArrayT) )
        print("T_SpectrumAnalysis: SMAPE = {0:.2f}".format(SMAPE))

        tmpIndex = np.argsort(tmpArraySMAPE) # 将 tmpArraySMAPE 升序排列得到的 索引

        T = tmpArrayT[tmpIndex[0]]
        T = np.mean(tmpArrayT[(0.65*T<tmpArrayT)&(tmpArrayT<1.35*T)])
        if SMAPE < tmpThreshold: # wfr 20201231 对称平均百分误差较小则认为稳定, 停止测量
            isStable = True
            MeasureDurationNext = -1
        elif tmpThreshold <= SMAPE and SMAPE < 0.15:
            isStable = False
            if MeasureDuration > 2.1 * TUpBound:
                MeasureDurationNext = -1
            # 测量够 MeasureTFactor倍 周期
            elif MeasureDuration < MeasureTFactor * np.max(arrayT):
                MeasureDurationNext = MeasureTFactor * np.max(arrayT) - MeasureDuration + 5
            else:
                MeasureDurationNext = np.ceil(MeasureDuration / np.max(arrayT)) * np.max(arrayT) - MeasureDuration + 5
        elif 0.15 <= SMAPE: # 最近几次周期相差较大, 测量区间远大于最近的最大周期
            isStable = False
            if MeasureDuration > 2.1 * TUpBound:
                MeasureDurationNext = -1
            elif MeasureDuration > TUpBound and T < 0.5 * TUpBound:
                MeasureDurationNext = -1
            elif MeasureDuration >= 1.3 * MeasureTFactor * np.max(arrayT):
                MeasureDurationNext = -1
            else:
                tmpTMax = np.max(tmpArrayT)
                MeasureDurationNext = MeasureTFactor * tmpTMax - MeasureDuration
                if MeasureDurationNext < 0:
                    MeasureDurationNext = tmpTMax * ( np.ceil(MeasureDuration/tmpTMax) + 1 - MeasureTFactor )
    if 0 < MeasureDurationNext and MeasureDurationNext < 5: # wfr 20210110 下次等待测量时间要 > 5s
        MeasureDurationNext += 5

    # wfr 20210116 这里使用新方法判断是否是无周期 5 * T
    if isStable == False and SMAPE > 0.4 and (LenT >= LenMax or MeasureDuration >= 5 * T or MeasureDuration > TUpBound):
        if True == NotPeriodic(arraySample, SampleInterval, T):
            # if T < TLowBound:
            #     T = np.ceil(TLowBound / T) * T
            MeasureDurationNext = -1
        
    if MeasureDurationNext > 0:
        MeasureDurationNext = max(0.5 * tmpT, (MeasureTFactor * tmpT - MeasureDuration)) # 测量够 5倍 周期
    print("T_SpectrumAnalysis: TOpt = {0:.2f} s".format(T))
    print("T_SpectrumAnalysis: isStable = {0}".format(isStable))
    print("T_SpectrumAnalysis: MeasureDurationNext = {0}".format(MeasureDurationNext))

    return T, isStable, MeasureDurationNext

    # 怎么处理周期较长的情况(例如>66s)
