/*******************************************************************************
Copyright(C), 2020-2020, 瑞雪轻飏
     FileName: main.cpp
       Author: 瑞雪轻飏
      Version: 0.01
Creation Date: 20200820
  Description: 测试 CUPTI 能否测量部分 kernel
       Others: 
*******************************************************************************/

#include "EPOpt.h"
#include <nvml.h>
#include <cuda.h>
#include <cuda_runtime.h>
#include <cupti.h>
#include <cupti_target.h>
#include <cupti_profiler_target.h>
#include <nvperf_host.h>
#include <nvperf_target.h>
#include <nvperf_cuda_host.h>
#include <cuda.h>
#include <unistd.h>
#include <stdio.h>
#include <typeinfo>
#include <time.h>
#include <sys/time.h>

#define NVPW_API_CALL(apiFuncCall)                                             \
do {                                                                           \
    NVPA_Status _status = apiFuncCall;                                         \
    if (_status != NVPA_STATUS_SUCCESS) {                                      \
        fprintf(stderr, "%s:%d: error: function %s failed with error %d.\n",   \
                __FILE__, __LINE__, #apiFuncCall, _status);                    \
        exit(-1);                                                              \
    }                                                                          \
} while (0)

#define CUPTI_API_CALL(apiFuncCall)                                            \
do {                                                                           \
    CUptiResult _status = apiFuncCall;                                         \
    if (_status != CUPTI_SUCCESS) {                                            \
        fprintf(stderr, "%s:%d: error: function %s failed with error %d.\n",   \
                __FILE__, __LINE__, #apiFuncCall, _status);                    \
        exit(-1);                                                              \
    }                                                                          \
} while (0)

#define DRIVER_API_CALL(apiFuncCall)                                           \
do {                                                                           \
    CUresult _status = apiFuncCall;                                            \
    if (_status != CUDA_SUCCESS) {                                             \
        fprintf(stderr, "%s:%d: error: function %s failed with error %d.\n",   \
                __FILE__, __LINE__, #apiFuncCall, _status);                    \
        exit(-1);                                                              \
    }                                                                          \
} while (0)

#define RUNTIME_API_CALL(apiFuncCall)                                          \
do {                                                                           \
    cudaError_t _status = apiFuncCall;                                         \
    if (_status != cudaSuccess) {                                              \
        fprintf(stderr, "%s:%d: error: function %s failed with error %s.\n",   \
                __FILE__, __LINE__, #apiFuncCall, cudaGetErrorString(_status));\
        exit(-1);                                                              \
    }                                                                          \
} while (0)

// #define METRIC_NAME "sm__warps_launched.avg+"
// #define METRIC_NAME "sm__inst_executed.avg.per_cycle_active"
#define METRIC_NAME "sm__inst_executed.max"

ENERGY_PERFORMANCE_OPTIMIZER EPOptDrv;
static void* MeasureMetric(void* Argv);

// Device code
__global__ void VecAdd(const int* A, const int* B, int* C, int N)
{
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    // while(true){
    //     if (i < N){
    //         C[i] = A[i] + B[i];
    //         C[i] -= A[i];
    //         C[i] -= B[i];
    //     }
    // }
    if (i < N){
        C[i] = A[i] + B[i];
    }
}

// Device code
__global__ void VecSub(const int* A, const int* B, int* C, int N)
{
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    if (i < N)
        C[i] = A[i] - B[i];
}

static void initVec(int *vec, int n)
{
  for (int i=0; i< n; i++)
    vec[i] = i;
}


static void cleanUp(int *h_A, int *h_B, int *h_C, int *h_D, int *d_A, int *d_B, int *d_C, int *d_D)
{
  if (d_A)
    cudaFree(d_A);
  if (d_B)
    cudaFree(d_B);
  if (d_C)
    cudaFree(d_C);
  if (d_D)
    cudaFree(d_D);

  // Free host memory
  if (h_A)
    free(h_A);
  if (h_B)
    free(h_B);
  if (h_C)
    free(h_C);
  if (h_D)
    free(h_D);
}

static void RunCUDAKernel()
{

    int N = 50000;
    size_t size = N * sizeof(int);
    int threadsPerBlock = 0;
    int blocksPerGrid = 0;
    int *h_A, *h_B, *h_C, *h_D;
    int *d_A, *d_B, *d_C, *d_D;
    int i, sum, diff;

    // Allocate input vectors h_A and h_B in host memory
    h_A = (int*)malloc(size);
    h_B = (int*)malloc(size);
    h_C = (int*)malloc(size);
    h_D = (int*)malloc(size);

    // Initialize input vectors
    initVec(h_A, N);
    initVec(h_B, N);
    memset(h_C, 0, size);
    memset(h_D, 0, size);

    // Allocate vectors in device memory
    cudaMalloc((void**)&d_A, size);
    cudaMalloc((void**)&d_B, size);
    cudaMalloc((void**)&d_C, size);
    cudaMalloc((void**)&d_D, size);

    // Copy vectors from host memory to device memory
    cudaMemcpy(d_A, h_A, size, cudaMemcpyHostToDevice);
    cudaMemcpy(d_B, h_B, size, cudaMemcpyHostToDevice);

    // Invoke kernel
    threadsPerBlock = 256;
    blocksPerGrid = (N + threadsPerBlock - 1) / threadsPerBlock;
    printf("Launching kernel: blocks %d, thread/block %d\n",
            blocksPerGrid, threadsPerBlock);

    VecAdd<<<blocksPerGrid, threadsPerBlock>>>(d_A, d_B, d_C, N);

    VecSub<<<blocksPerGrid, threadsPerBlock>>>(d_A, d_B, d_D, N);

    // Copy result from device memory to host memory
    // h_C contains the result in host memory
    cudaMemcpy(h_C, d_C, size, cudaMemcpyDeviceToHost);
    cudaMemcpy(h_D, d_D, size, cudaMemcpyDeviceToHost);

    // Verify result
    for (i = 0; i < N; ++i) {
        sum = h_A[i] + h_B[i];
        diff = h_A[i] - h_B[i];
        if (h_C[i] != sum || h_D[i] != diff) {
        fprintf(stderr, "error: result verification failed\n");
        exit(-1);
        }
    }

    cleanUp(h_A, h_B, h_C, h_D, d_A, d_B, d_C, d_D);
}

int main(int argc, char* argv[])
{
    int deviceCount, deviceNum;
    char* metricName;
    std::vector<std::string> vecMetricName;
    CUdevice cuDevice;
    CUcontext cuContext;

    DRIVER_API_CALL(cuInit(0));
    DRIVER_API_CALL(cuDeviceGetCount(&deviceCount));

    if (deviceCount == 0) {
        printf("There is no device supporting CUDA.\n");
        return -2;
    }

    if (argc > 1)
        deviceNum = atoi(argv[1]);
    else
        deviceNum = 1;
    printf("CUDA Device Number: %d\n", deviceNum);

    DRIVER_API_CALL(cuDeviceGet(&cuDevice, deviceNum));
    DRIVER_API_CALL(cuCtxCreate(&cuContext, 0, cuDevice));
    std::cout << "cuContext = 0x" << std::hex << (void*)cuContext << std::dec << std::endl;
    // DRIVER_API_CALL(cuCtxSetCurrent(cuContext));

    // Get the names of the metrics to collect
    if (argc > 2) {
        metricName = strtok(argv[2], ",");
        while(metricName != NULL)
        {
            vecMetricName.push_back(metricName);
            metricName = strtok(NULL, ",");
        }
    }
    else {
        vecMetricName.push_back(METRIC_NAME);
    }

    EPOptDrv.Init(deviceNum, deviceNum, true, true);

    // 这里启动新线程，测量 GPU 性能特征
    pthread_t TID;
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
    void* Argv[3];

    Argv[0] = (void*)(&vecMetricName);
    Argv[1] = (void*)(&cuContext);
    // Argv[BufIndex][2] = (void*)buf[BufIndex];

    int err = pthread_create(&TID, &attr, MeasureMetric, (void*)Argv);
    if(err != 0) {
        std::cerr << "ERROR: pthread_create() return code: " << err << std::endl;
        exit(1);
    }

    // double SleepTime = 2.0;
    // double StartTimeStamp;
    // struct timeval TimeStruct;

    // std::cout << "sleep(2)" << std::endl;
    // gettimeofday(&TimeStruct,NULL);
    // StartTimeStamp = (double)TimeStruct.tv_sec + (double)TimeStruct.tv_usec * 1e-6;

    // while((double)TimeStruct.tv_sec + (double)TimeStruct.tv_usec * 1e-6 - StartTimeStamp < SleepTime){
    //     gettimeofday(&TimeStruct,NULL);
    // }
    // std::cout << "sleep(2) completes" << std::endl;



    // std::cout << "EPOptDrv.Begin()" << std::endl;
    // EPOptDrv.Begin(vecMetricName);

    // 这里启动 CUDA kernel
    std::cout << "启动 CUDA kernel" << std::endl;
    for(int i = 0; i < 8; i++){
        RunCUDAKernel();
        double SleepTime = 1.0;
        double StartTimeStamp;
        struct timeval TimeStruct;

        std::cout << "kernel sleep(1)" << std::endl;
        gettimeofday(&TimeStruct,NULL);
        StartTimeStamp = (double)TimeStruct.tv_sec + (double)TimeStruct.tv_usec * 1e-6;

        while((double)TimeStruct.tv_sec + (double)TimeStruct.tv_usec * 1e-6 - StartTimeStamp < SleepTime){
            gettimeofday(&TimeStruct,NULL);
        }
        std::cout << "kernel sleep(1) completes" << std::endl;
    }

    // EPOptDrv.End(1);
    // std::cout << "EPOptDrv.End()" << std::endl;




    // DRIVER_API_CALL(cuCtxDestroy(cuContext));
    std::cout << "CUDA kernel completes" << std::endl;

    while(true){}

    return 0;
}

static void* MeasureMetric(void* Argv){

    std::vector<std::string>& vecMetricName = *(((std::vector<std::string>**)Argv)[0]);
    CUcontext cuContext = *(  ((CUcontext**)Argv)[1]  );

    // std::cout << "开始获取 cuContext" << std::endl;

    // while 直到有 CUDA context 被创建
    // while((void*)cuContext == NULL){
    //     DRIVER_API_CALL(cuCtxGetCurrent(&cuContext));
    //     std::cout << "cuContext = 0x" << std::hex << (void*)cuContext << std::dec << std::endl;
    //     usleep(1000000);
    // }
    std::cout << "cuContext = 0x" << std::hex << (void*)cuContext << std::dec << std::endl;

    // DRIVER_API_CALL(cuInit(0));
    // DRIVER_API_CALL(cuCtxPushCurrent(cuContext));
    DRIVER_API_CALL(cuCtxSetCurrent(cuContext));

    CUcontext cuContext1;
    DRIVER_API_CALL(cuCtxGetCurrent(&cuContext1));
    std::cout << "cuContext1 = 0x" << std::hex << (void*)cuContext1 << std::dec << std::endl;
    
    // 延时
    // std::cout << "sleep(2)" << std::endl;
    sleep(2);

    std::cout << "\nEPOptDrv.Begin()" << std::endl;
    EPOptDrv.Begin(vecMetricName);

    // 延时
    // std::cout << "sleep(3)" << std::endl;
    // sleep(3);
    // std::cout << "sleep(3) completes" << std::endl;

    double SleepTime = 5.0;
    double StartTimeStamp;
    struct timeval TimeStruct;

    std::cout << "EPOptDrv sleep(" << SleepTime << ")" << std::endl;
    gettimeofday(&TimeStruct,NULL);
    StartTimeStamp = (double)TimeStruct.tv_sec + (double)TimeStruct.tv_usec * 1e-6;

    while((double)TimeStruct.tv_sec + (double)TimeStruct.tv_usec * 1e-6 - StartTimeStamp < SleepTime){
        gettimeofday(&TimeStruct,NULL);
    }
    std::cout << "EPOptDrv sleep(" << SleepTime << ") completes" << std::endl;

    EPOptDrv.End(1);
    std::cout << "EPOptDrv.End()\n" << std::endl;

    pthread_exit(NULL);
}