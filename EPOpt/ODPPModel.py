import random
import numpy as np
import numpy
import matplotlib.pyplot as plt
import time
import os
os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

import tensorflow as tf
from tensorflow.keras import Sequential, layers, optimizers

def FindIndex(arrayAll, arrayTarget):
    arrayIndex = np.searchsorted(arrayAll, arrayTarget)
    arrayIndex[arrayIndex==len(arrayAll)] = len(arrayAll) - 1
    if len(arrayIndex) != len(np.unique(arrayIndex)):
        print("FindIndex ERROR: Duplicate sample points")
        os._exit()
    return arrayIndex

class ODPP_AM():
    def __init__(self, arraySampleClock=np.array([]), arrayClock=np.array([]), arrayTarget=np.array([])):
        if len(arraySampleClock) > 0 and len(arrayClock) > 0 and len(arrayTarget) > 0:
            tmpIndex = np.argsort(arraySampleClock)
            self.SampleClocks = arraySampleClock[tmpIndex]
            arrayIndex = FindIndex(arrayClock, arraySampleClock)
            self.SampleTargets = arrayTarget[arrayIndex]

    def Init(self, arraySampleClock, arrayClock, arrayTarget):
        tmpIndex = np.argsort(arraySampleClock)
        self.SampleClocks = arraySampleClock[tmpIndex]
        arrayIndex = FindIndex(arrayClock, arraySampleClock)
        self.SampleTargets = arrayTarget[arrayIndex]

    def Predict(self, clock):
        value = 0.0

        if type(clock) is not numpy.ndarray and type(clock) is not list:
            clock = np.array([clock])

        value = np.zeros(len(clock))
        for i in range(len(clock)):
            tmpIndex = np.argwhere(clock[i] == self.SampleClocks).flatten()
            if len(tmpIndex) > 0:
                value[i]  = self.SampleTargets[tmpIndex[0]]
            else:
                tmpIndex = np.argwhere(self.SampleClocks < clock[i]).flatten()
                if len(tmpIndex) > 0:
                    i0 = tmpIndex[-1]
                else:
                    i0 = 0
                tmpIndex = np.argwhere(clock[i] < self.SampleClocks).flatten()
                if len(tmpIndex) > 0:
                    i1 = tmpIndex[0]
                else:
                    i1 = - 1
                value[i] = self.SampleTargets[i0] + (self.SampleTargets[i1]-self.SampleTargets[i0]) / (self.SampleClocks[i1]-self.SampleClocks[i0]) * (clock[i] - self.SampleClocks[i0])

        if len(value) == 1:
            value = value[0]

        return value

class ODPP_AM_MLP():
    def __init__(self):
        self.AM = ODPP_AM()
        self.MLP = Sequential([
            layers.Flatten(input_shape=(5,)),
            layers.BatchNormalization(),
            layers.Dense(46, activation='relu'),
            layers.Dense(92, activation='relu'),
            layers.Dense(92, activation='relu'),
            layers.Dense(1)
        ])
        self.MLP.summary()
        self.MLP.compile(optimizer=optimizers.Adam(), loss='mse')

    def TrainMLP(self, arrayMLPFeature, arrayTarget, inBatchSize, inEpochs, ModelName="Model name is empty"):

        arrayTarget = arrayTarget.reshape(-1, 1)
        tensorMLPFeature = tf.convert_to_tensor(arrayMLPFeature, tf.float32)
        tensorTarget = tf.convert_to_tensor(arrayTarget, tf.float32)

        print("{}".format(ModelName))
        print(self.MLP)
        self.MLP.fit(tensorMLPFeature, tensorTarget, batch_size=inBatchSize, epochs=inEpochs, steps_per_epoch=1)
        return

    def RetrainMLP(self, arrayCalibrateClock, arrayClock, arrayTarget, arrayFeature, inBatchSize, inEpochs, ModelName="Model name is empty"):
        arrayIndex = FindIndex(arrayClock, arrayCalibrateClock)
        arrayClock = arrayClock[arrayIndex]
        arrayTarget = arrayTarget[arrayIndex]
        arrayFeature = arrayFeature[arrayIndex]

        arrayAMOut = self.AM.Predict(arrayClock).reshape(-1,1)
        arrayMLPFeature = np.hstack([arrayAMOut, arrayFeature])

        self.TrainMLP(arrayMLPFeature, arrayTarget, inBatchSize, inEpochs, ModelName)
        return

    def Predict(self, arrayClock, arrayFeature):
        arrayAMOut = self.AM.Predict(arrayClock).reshape(-1,1)
        arrayMLPFeature = np.hstack([arrayAMOut, arrayFeature])
        arrayMLPOut = self.MLP.predict(tf.convert_to_tensor(arrayMLPFeature, tf.float32), steps=1)

        return arrayMLPOut