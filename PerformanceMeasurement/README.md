# PerformanceMeasurement

PerformanceMeasurement has three run modes.

# measure as daemon (recommended mode)
PerfMeasure.bin -e -s 100 -t 30
sudo ./PerfMeasure.bin -e -i 1 -s 100 -t 30 -m DAEMON

-i: GPU ID queried with nvidia-smi
-e: energy measurement flag
-s: sample interval (ms)
-t: static power threshold (W)
-trace: enable trace recording for: Time Stamp (s), Power (W), GPUUtil (%), SMClk (MHz), MemUtil (%), MemClk (MHz)

You can control the PerfMeasure deamon through UDP messages. The available UDP messages are implemented with three languages: Msg2EPRT.sh Msg2EPRT.py Msg2EPRT.cpp

# measure without applications
sudo PerfMeasure.bin -e -s 100 -t 30

# measure applications
sudo PerfMeasure.bin -e -s 100 -t 30 -o ./path_of_output_file.log -a ./path_of_applicaiton.bin <application arguments>

-o: path of output file
-a: path of applicaiton <application arguments>


sudo PerfMeasure.bin -e -s 100 -t 30 -l ./path_of_application_list_file.txt -o ./path_of_output_file.log

application list file format:
./path_of_applicaiton1.bin <application arguments>
./path_of_applicaiton2.bin <application arguments>
./path_of_applicaiton3.bin <application arguments>








