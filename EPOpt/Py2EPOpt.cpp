
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/complex.h>
#include <pybind11/functional.h>
#include <pybind11/chrono.h>
#include "EPOpt.h"

ENG_PERF_MANAGER Manager;
ENG_PERF_MEASURER Measurer;

int MeasurerInitInCode(int inDeviceIDCUDADrv, int inDeviceIDNVML, int inRunMode, std::vector<std::string> inVecMetricName, bool inIsMeasurePower = true, bool inIsMeasurePerformace = true){
    return Measurer.InitInCode(inDeviceIDCUDADrv, inDeviceIDNVML, (RUN_MODE) inRunMode, inVecMetricName, inIsMeasurePower, inIsMeasurePerformace);
}

int MeasurerBeginInCode(){
    return Measurer.BeginInCode();
}

std::map<std::string, double> MeasurerEndInCode(){
    std::map<std::string, double> mapMetricNameValue;
    Measurer.EndInCode(mapMetricNameValue);
    return mapMetricNameValue;
}

int MeasurerInit(int inDeviceIDCUDADrv, int inDeviceIDNVML, 
    int inRunMode, int inMeasureMode, std::vector<std::string> inVecMetricName, 
    float inMeasureDuration = 0, bool inIsMeasurePower = true, 
    bool inIsMeasurePerformace = true)
{
    return Measurer.Init(inDeviceIDCUDADrv, inDeviceIDNVML, (RUN_MODE) inRunMode, (MEASURE_MODE)inMeasureMode, inVecMetricName, inMeasureDuration, inIsMeasurePower, inIsMeasurePerformace);
}

int MeasurerSendStopSignal2Manager(){
    return Measurer.SendStopSignal2Manager();
}

int MeasurerStop(){
    return Measurer.Stop();
}

int ManagerInit(int inDeviceIDNVML, int inRunMode, int inMeasureMode){
    return Manager.Init(inDeviceIDNVML, (RUN_MODE)inRunMode, (MEASURE_MODE)inMeasureMode);
}

int ManagerStop(){
    return Manager.Stop();
}

// MeasureAndReceiveData

int MeasureDuration(std::vector<std::string> inVecMetricName, std::string MeasureBeginSignal, float SampleDuration){
    return Manager.StartMeasure(inVecMetricName, MeasureBeginSignal, MEASURE_MODE::TIMER, SampleDuration);
}

int StartMeasure(std::vector<std::string> inVecMetricName, std::string MeasureBeginSignal){
    return Manager.StartMeasure(inVecMetricName, MeasureBeginSignal, MEASURE_MODE::SIGNAL, 0);
}

int ReceiveData(){
    return Manager.ReceiveData();
}

int StopMeasure(){
    return Manager.StopMeasure();
}

std::map< std::string, double > GetFeature(){
    return Manager.GetFeature();
}

std::vector< float > GetPowerTrace(){
    return Manager.GetPowerTrace();
}

std::vector< int > GetSMUtilTrace(){
    return Manager.GetSMUtilTrace();
}

std::vector< int > GetMemUtilTrace(){
    return Manager.GetMemUtilTrace();
}

int GetSMClkGearCount(){
    return Manager.PowerManager.GetSMClkGearCount();
}

int GetBaseSMClk(){
    return Manager.PowerManager.GetBaseSMClk();
}

int GetMinSMClk(){
    return Manager.PowerManager.GetMinSMClk();
}

int GetSMClkStep(){
    return Manager.PowerManager.GetSMClkStep();
}

int GetCurrGPUUtil(){
    return Manager.GetCurrGPUUtil();
}

int GetCurrSMClk(){
    return Manager.GetCurrSMClk();
}

int GetCurrMemClk(){
    return Manager.GetCurrMemClk();
}

float GetPowerLimit(){
    return Manager.GetPowerLimit();
}

int NVMLInit(){
    return Manager.NVMLInit();
}

int NVMLUninit(){
    return Manager.NVMLUninit();
}

std::string GetGPUName(){
    return Manager.PowerManager.GetGPUName();
}

int SetEnergyGear(int EnergyGear){
    return Manager.PowerManager.SetSMClkGear(EnergyGear);
}

int SetSMClkRange(int LowerSMClk, int UpperSMClk){
    return Manager.PowerManager.SetSMClkRange(LowerSMClk, UpperSMClk);
}

int SetMemClkRange(int LowerMemClk, int UpperMemClk){
    return Manager.PowerManager.SetMemClkRange(LowerMemClk, UpperMemClk);
}

int ResetMemClkRange(){
    return Manager.PowerManager.ResetMemClkRange();
}

int ResetEnergyGear(){
    return Manager.PowerManager.ResetSMClkRange();
}

PYBIND11_MODULE(EPOptDrv, m) {
    m.doc() = "EPOptDrv plugin"; // optional module docstring

    m.def("MeasurerInitInCode", &MeasurerInitInCode, "Measurer Init function used in python source code");
    m.def("MeasurerBeginInCode", &MeasurerBeginInCode, "Measurer Init function used in python source code");
    m.def("MeasurerEndInCode", &MeasurerEndInCode, "Measurer Init function used in python source code");

    m.def("MeasurerInit", &MeasurerInit, "Measurer Init function");
    m.def("MeasurerSendStopSignal2Manager", &MeasurerSendStopSignal2Manager, "Measurer send stop signal ");
    m.def("MeasurerStop", &MeasurerStop, "Measurer Stop function");

    m.def("ManagerInit", &ManagerInit, "Manager Init function");
    m.def("ManagerStop", &ManagerStop, "Manager Stop function");

    m.def("MeasureDuration", &MeasureDuration, "MeasureDuration");
    m.def("StartMeasure", &StartMeasure, "StartMeasure");
    m.def("ReceiveData", &ReceiveData, "ReceiveData");
    m.def("StopMeasure", &StopMeasure, "StopMeasure");
    m.def("GetPowerTrace", &GetPowerTrace, "GetPowerTrace");
    m.def("GetSMUtilTrace", &GetSMUtilTrace, "GetSMUtilTrace");
    m.def("GetMemUtilTrace", &GetMemUtilTrace, "GetMemUtilTrace");
    m.def("GetFeature", &GetFeature, "GetFeature");
    
    m.def("GetSMClkGearCount", &GetSMClkGearCount);
    m.def("GetBaseSMClk", &GetBaseSMClk);
    m.def("GetMinSMClk", &GetMinSMClk);
    m.def("GetSMClkStep", &GetSMClkStep);
    m.def("GetGPUName", &GetGPUName);
    m.def("GetCurrGPUUtil", &GetCurrGPUUtil);
    m.def("GetCurrSMClk", &GetCurrSMClk);
    m.def("GetCurrMemClk", &GetCurrMemClk);
    m.def("GetPowerLimit", &GetPowerLimit);
    m.def("NVMLInit", &NVMLInit);
    m.def("NVMLUninit", &NVMLUninit);
    
    m.def("SetEnergyGear", &SetEnergyGear);
    m.def("ResetEnergyGear", &ResetEnergyGear);
    m.def("SetMemClkRange", &SetMemClkRange);
    m.def("ResetMemClkRange", &ResetMemClkRange);

}

