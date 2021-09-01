# PerformanceMeasurement

# measure without applications
PerfMeasure.bin -e -s 20 -t 20

-e: energy measurement flag
-s: sample interval (ms)
-t: static power threshold (W)


# measure applications
PerfMeasure.bin -e -s 20 -t 20 -o /path_of_output_file -a /path_of_applicaiton <application arguments>

-o: /path_of_output_file
-a: /path_of_applicaiton <application arguments>

PerfMeasure.bin -s 20 -t 20 -l /path_of_application_list_file -o /path_of_output_file

application list file format:
/path_of_applicaiton1 <application arguments>
/path_of_applicaiton2 <application arguments>
/path_of_applicaiton3 <application arguments>






sudo ./PerfMeasure.bin -e -i 1 -s 20 -t 1.65 -m DAEMON -o ./test.txt

