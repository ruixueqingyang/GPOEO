/*******************************************************************************
Copyright(C), 2020-2021, 瑞雪轻飏
     FileName: EPOptAPI.cpp
       Author: 瑞雪轻飏
      Version: 0.01
Creation Date: 20210315
  Description: profile energy/power and performance data
               optimize energy-performance jointly
       Others: 
*******************************************************************************/

#include "EPOptAPI.h"

PyObject* EPOptInstance;
std::string vecRunMode[4] = {"WORK", "LEARN", "LEARN_WORK", "MEASURE"};

// inDeviceIDCUDADrv, inDeviceIDNVML, inRunMode="LEARN", inMeasureOutDir="NONE", inQTableDir="/home/wfr/work/Energy/EPOpt/QTable", inTestPrefix=""

std::string qtable_dir = "/home/wfr/work/Energy/EPOpt/QTable";
std::string test_prefix = "lammps";
std::string run_mode = "WORK";
std::string measure_out_dir = "NONE";
int GPUIDCUDADrv = 1;
int GPUIDNVML = 1;
bool EP = false;

int ParseOptions(int& argc, char** argv){
    
    int err = 0;
    unsigned int indexArg = 1; // the first arg is the path of bin, ignore it, so indexArg = 1, 当前 flag(即-xxxx) 在 argv 中的 index
    extern int optind,opterr,optopt;
    opterr = 0; // do not print error to stderr
    extern char *optarg;
    // const char usage[] = "Usage: %s [-e] \nType '??? -h' for help.\n";
    std::vector<int> vecIndex;

    // make a copy of argv, because getopt_long_only() will disorder argv
    int MyArgc = argc;
    char** MyArgv = (char**)malloc(argc * sizeof(char*));
    for (size_t i = 0; i < argc; i++)
    {
        MyArgv[i] = argv[i];
    }

    //定义长选项
    static struct option long_options[] = 
    {
        {"h", no_argument, NULL, 'h'},
        {"help", no_argument, NULL, 'h'},

        {"qtable_dir", required_argument, NULL, 'q'},
        {"measure_out_dir", required_argument, NULL, 's'},
        {"test_prefix", required_argument, NULL, 't'},

        {"gpu_id_cudrv", required_argument, NULL, 'd'},
        {"gpu_id_nvml", required_argument, NULL, 'n'},
        {"EP", required_argument, NULL, 'o'},
        {"run_mode", required_argument, NULL, 'm'},
    };

    int qSet=0, sSet=0, tSet=0, dSet=0, nSet=0, oSet=0, mSet=0, eSet=0;

    int c = 0; //用于接收选项
    /*循环处理参数*/
    while(EOF != (c = getopt_long_only(argc, argv, "", long_options, NULL))){
        //打印处理的参数
        //printf("start to process %d para\n",optind);
        switch(c){
            case 'h':
            {
                printf ("这里应该打印帮助信息...\n");
                //printf ( HELP_INFO );
                indexArg++;
                break;
            }
            case 'q':
            {
                if(qSet!=0){
                    std::cerr << "WARNING: --qtable_dir is set multiple times, the first value is used" << std::endl;
                    indexArg+=2;
                    break;
                }
                qSet++;
                vecIndex.emplace_back(indexArg);
                vecIndex.emplace_back(indexArg+1);
                indexArg+=2;
                qtable_dir = optarg;
                break;
            }
            case 's':
            {
                if(sSet!=0){
                    std::cerr << "WARNING: --measure_out_dir is set multiple times, the first value is used" << std::endl;
                    indexArg+=2;
                    break;
                }
                sSet++;
                vecIndex.emplace_back(indexArg);
                vecIndex.emplace_back(indexArg+1);
                indexArg+=2;
                measure_out_dir = optarg;
                break;
            }
            case 't':
            {
                if(tSet!=0){
                    std::cerr << "WARNING: --test_prefix is set multiple times, the first value is used" << std::endl;
                    indexArg+=2;
                    break;
                }
                tSet++;
                vecIndex.emplace_back(indexArg);
                vecIndex.emplace_back(indexArg+1);
                indexArg+=2;
                test_prefix = optarg;
                break;
            }
            case 'd':
            {
                if(dSet!=0){
                    std::cerr << "WARNING: --gpu_id_cudrv is set multiple times, the first value is used" << std::endl;
                    indexArg+=2;
                    break;
                }
                dSet++;
                vecIndex.emplace_back(indexArg);
                vecIndex.emplace_back(indexArg+1);
                indexArg+=2;
                GPUIDCUDADrv = atoi(optarg);
                break;
            }
            case 'n':
            {
                if(nSet!=0){
                    std::cerr << "WARNING: --gpu_id_nvml is set multiple times, the first value is used" << std::endl;
                    indexArg+=2;
                    break;
                }
                nSet++;
                vecIndex.emplace_back(indexArg);
                vecIndex.emplace_back(indexArg+1);
                indexArg+=2;
                GPUIDNVML = atoi(optarg);
                break;
            }
            case 'o':
            {
                if(oSet!=0){
                    std::cerr << "WARNING: --EP is set multiple times, the first value is used" << std::endl;
                    indexArg+=2;
                    break;
                }
                oSet++;
                vecIndex.emplace_back(indexArg);
                vecIndex.emplace_back(indexArg+1);
                indexArg+=2;
                if ( (0 == strncmp("True", optarg, 4)) || (0 == strncmp("true", optarg, 4)) ){
                    EP = true;
                }else{
                    EP = false;
                }
                break;
            }
            case 'm':
            {
                if(mSet!=0){
                    std::cerr << "WARNING: --run_mode is set multiple times, the first value is used" << std::endl;
                    indexArg+=2;
                    break;
                }
                mSet++;
                vecIndex.emplace_back(indexArg);
                vecIndex.emplace_back(indexArg+1);
                indexArg+=2;
                run_mode = optarg;
                break;
            }

            //表示选项不支持
            case '?':
            {
                // printf("unknow option:%c\n", optopt);
                // err |= 1;
                indexArg++;
                break;
            }
            default:
                break;
        }
    }
    
    // std::cout << "vecIndex: " << std::dec;
    // for (size_t i = 0; i < vecIndex.size(); i++)
    // {
    //     std::cout << vecIndex[i] << "; ";
    // }
    // std::cout << std::endl;

    // std::cout << "MyArgc = " << MyArgc << std::endl;
    // std::cout << "CLI: ";
    // for (size_t i = 0; i < MyArgc; i++)
    // {
    //     std::cout << MyArgv[i] << "; ";
    // }
    // std::cout << std::endl;

    // delete args used by EPOpt
    for (int i = vecIndex.size()-1; i >= 0; i--)
    {
        for (int j = vecIndex[i]; j < MyArgc-1; j++)
        {
            MyArgv[j] = MyArgv[j+1];
        }
        MyArgv[argc-1] = nullptr;
        --MyArgc;
    }

    // copy MyArgv back to argv
    for (size_t i = 0; i < argc; i++)
    {
        argv[i] = MyArgv[i];
    }
    argc = MyArgc;
    
    // std::cout << "CLI: ";
    // for (size_t i = 0; i < argc; i++)
    // {
    //     std::cout << argv[i] << "; ";
    // }
    // std::cout << std::endl;
        
    free(MyArgv);
    return err;
}

// int EPOptBegin(int DeviceIDCUDADrv, int DeviceIDNVML, RUN_MODE RunModeID, std::string MeasureOutDir, std::string QTableDir, std::string TestName){
int EPOptBegin(int& argc, char** argv){

    //打印pid
    std::cout << "EPOptBegin: PID = " << std::hex << getpid() << std::endl;
    //打印tid
    std::cout << "EPOptBegin: TID = " << std::hex << std::this_thread::get_id() << std::endl;

    ParseOptions(argc, argv);

    if (EP == false)
    {
        return 0;
    }
    

    Py_Initialize();
    // PyRun_SimpleString("print('Hello World form Python~')\n");
    PyRun_SimpleString("import sys");
    PyRun_SimpleString("import importlib.util, importlib.machinery");
    PyRun_SimpleString("loader = importlib.machinery.SourceFileLoader('PyEPOpt', '/home/wfr/work/Energy/EPOpt/PyEPOpt.py')");
    PyRun_SimpleString("spec = importlib.util.spec_from_loader(loader.name, loader)");
    PyRun_SimpleString("PyEPOpt = importlib.util.module_from_spec(spec)");
    PyRun_SimpleString("spec.loader.exec_module(PyEPOpt)");
    // std::cout << "EPOptBegin: 0" << std::endl;
	// PyRun_SimpleString("sys.path.append('/home/wfr/work/Energy/EPOpt/Python3.9')");
    // PyRun_SimpleString("print(sys.path)");
    PyObject * pModule = NULL;
    // PyObject * pFunc = NULL;
    pModule = PyImport_ImportModule("PyEPOpt");
    // std::cout << "EPOptBegin: 1" << std::endl;
    PyObject* pDict = PyModule_GetDict(pModule);
    // std::cout << "EPOptBegin: 2" << std::endl;
    PyObject* EPOptClass = PyDict_GetItemString(pDict,"EP_OPT");
    // std::cout << "EPOptBegin: 3" << std::endl;
    PyObject* EPOptConstruct = PyInstanceMethod_New(EPOptClass);
    // std::cout << "EPOptBegin: 4" << std::endl;
    EPOptInstance = PyObject_CallObject(EPOptConstruct, nullptr);
    std::cout << "EPOptBegin: call PyEPOpt" << std::endl;
    // 可以直接调用 类的方法, 也可以先获得 类的方法为 PyObject 再调用
    PyObject_CallMethod(EPOptInstance, "Begin", "iissss", GPUIDCUDADrv, GPUIDNVML, run_mode.c_str(), measure_out_dir.c_str(), qtable_dir.c_str(), test_prefix.c_str());

    return 0;
}

int EPOptEnd(){

    if (EP == false)
    {
        return 0;
    }

    PyObject_CallMethod(EPOptInstance, "End", nullptr);
    Py_Finalize();

    return 0;
}

int SendUDPMessage(std::string Msg);

int SetSMClkRange(float LowerPercent, float UpperPercent){
    std::string Msg = "SM_RANGE: ";
    Msg = Msg + std::to_string(LowerPercent) + ", " + std::to_string(UpperPercent);
    return SendUDPMessage(Msg);
}

int TimeStamp(std::string Description){
    std::string Msg = "TIME_STAMP: ";
    Msg = Msg + Description;
    return SendUDPMessage(Msg);
}

int StartMeasurement(){
    return SendUDPMessage("START");
}

int StopMeasurement(){
    return SendUDPMessage("STOP");
}

int ExitMeasurement(){
    return SendUDPMessage("EXIT");
}

int ResetMeasurement(){
    return SendUDPMessage("RESET");
}

int ResetMeasurement(std::string OutPath){
    std::string Msg = "RESET: ";
    Msg += OutPath;
    return SendUDPMessage(Msg);
}

int SendUDPMessage(std::string Msg){
    int client_fd;
    struct sockaddr_in ser_addr;

    client_fd = socket(AF_INET, SOCK_DGRAM, 0);
    if(client_fd < 0){
        std::cout << "WARNING: create socket fail!\n" << std::endl;
        return -1;
    }

    memset(&ser_addr, 0, sizeof(ser_addr));
    ser_addr.sin_family = AF_INET;
    //ser_addr.sin_addr.s_addr = inet_addr(SERVER_IP);
    ser_addr.sin_addr.s_addr = htonl(INADDR_ANY);  //注意网络序转换
    ser_addr.sin_port = htons(SERVER_PORT);  //注意网络序转换

    socklen_t SizeofSockAddr = sizeof(ser_addr);
    // sendto(client_fd, Msg.c_str(), BUFF_LEN, 0, (struct sockaddr*)&ser_addr, SizeofSockAddr);
    sendto(client_fd, Msg.c_str(), Msg.size()+1, 0, (struct sockaddr*)&ser_addr, SizeofSockAddr);

    close(client_fd);

    return 0;
}