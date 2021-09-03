/*******************************************************************************
Copyright(C), 2020-2020, 瑞雪轻飏
     FileName: CheckError.h
       Author: 瑞雪轻飏
      Version: 0.01
Creation Date: 20200731
  Description: 1. 包含各种头文件
               2. 定义 可用的频率对
       Others: //其他内容说明
*******************************************************************************/

#ifndef __CHECK_ERROR_H
#define __CHECK_ERROR_H

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

#ifndef NVPW_API_CALL
#define NVPW_API_CALL(apiFuncCall)                                             \
do {                                                                           \
    NVPA_Status _status = apiFuncCall;                                         \
    if (_status != NVPA_STATUS_SUCCESS) {                                      \
        fprintf(stderr, "%s:%d: error: function %s failed with error %d.\n",   \
                __FILE__, __LINE__, #apiFuncCall, _status);                    \
        exit(-1);                                                              \
    }                                                                          \
} while (0)
#endif

#ifndef CHECK_NVPW_ERROR
#define CHECK_NVPW_ERROR(err) \
do{ \
    int tmpErrFlag = __checkNVPWError(err, __FILE__, __LINE__); \
    if(tmpErrFlag!=0) return tmpErrFlag; \
}while(0)
#define checkNVPWError(err) __checkNVPWError(err, __FILE__, __LINE__)

inline int __checkNVPWError(NVPA_Status err, const char *file, const int line) {
  if (NVPA_STATUS_SUCCESS != err) {
    // const char *errorStr = NULL;
    // cuptiGetResultString(err, &errorStr);
    fprintf(stderr,
            "checkNVPWError() NVPW API error = %04d from file <%s>, "
            "line %i.\n",
            err, file, line);
    return -1;
  }
  return 0;
}
#endif

#ifndef CUPTI_API_CALL
#define CUPTI_API_CALL(apiFuncCall)                                            \
do {                                                                           \
    CUptiResult _status = apiFuncCall;                                         \
    if (_status != CUPTI_SUCCESS) {                                            \
        fprintf(stderr, "%s:%d: error: function %s failed with error %d.\n",   \
                __FILE__, __LINE__, #apiFuncCall, _status);                    \
        exit(-1);                                                              \
    }                                                                          \
} while (0)
#endif

#ifndef CHECK_CUPTI_ERROR
#define CHECK_CUPTI_ERROR(err) \
do{ \
    int tmpErrFlag = __checkCUPTIError(err, __FILE__, __LINE__); \
    if(tmpErrFlag!=0) return tmpErrFlag; \
}while(0)
#define checkCUPTIError(err) __checkCUPTIError(err, __FILE__, __LINE__)

inline int __checkCUPTIError(CUptiResult err, const char *file, const int line) {
  if (CUPTI_SUCCESS != err) {
    const char *errorStr = NULL;
    cuptiGetResultString(err, &errorStr);
    fprintf(stderr,
            "checkCUPTIError() CUPTI API error = %04d \"%s\" from file <%s>, "
            "line %i.\n",
            err, errorStr, file, line);
    return -1;
  }
  return 0;
}
#endif

#ifndef DRIVER_API_CALL
#define DRIVER_API_CALL(apiFuncCall)                                           \
do {                                                                           \
    CUresult _status = apiFuncCall;                                            \
    if (_status != CUDA_SUCCESS) {                                             \
        fprintf(stderr, "%s:%d: error: function %s failed with error %d.\n",   \
                __FILE__, __LINE__, #apiFuncCall, _status);                    \
        exit(-1);                                                              \
    }                                                                          \
} while (0)
#endif

#ifndef CHECK_CUDA_DRIVER_ERROR
#define CHECK_CUDA_DRIVER_ERROR(err) \
do{ \
    int tmpErrFlag = __checkCudaDriverError(err, __FILE__, __LINE__); \
    if(tmpErrFlag!=0) return tmpErrFlag; \
}while(0)
#define checkCudaDriverError(err) __checkCudaDriverError(err, __FILE__, __LINE__)

inline int __checkCudaDriverError(CUresult err, const char *file, const int line) {
  if (CUDA_SUCCESS != err) {
    const char *errorStr = NULL;
    cuGetErrorString(err, &errorStr);
    fprintf(stderr,
            "checkCudaDriverError() Driver API error = %04d \"%s\" from file <%s>, "
            "line %i.\n",
            err, errorStr, file, line);
    return -1;
  }
  return 0;
}
#endif

#ifndef RUNTIME_API_CALL
#define RUNTIME_API_CALL(apiFuncCall)                                          \
do {                                                                           \
    cudaError_t _status = apiFuncCall;                                         \
    if (_status != cudaSuccess) {                                              \
        fprintf(stderr, "%s:%d: error: function %s failed with error %s.\n",   \
                __FILE__, __LINE__, #apiFuncCall, cudaGetErrorString(_status));\
        exit(-1);                                                              \
    }                                                                          \
} while (0)
#endif


#endif