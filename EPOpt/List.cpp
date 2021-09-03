#include <List.h>
#include <iostream>
#include <nvperf_host.h>
#include <nvperf_cuda_host.h>
#include <ScopeExit.h>

#define RETURN_IF_NVPW_ERROR(retval, actual) \
    do { \
        if (NVPA_STATUS_SUCCESS != actual) { \
            fprintf(stderr, "FAILED: %s\n", #actual); \
            return retval; \
        } \
    } while (0)

namespace NV {
    namespace Metric {
        namespace Enum {
            bool ListSupportedChips() {
                NVPW_GetSupportedChipNames_Params getSupportedChipNames = { NVPW_GetSupportedChipNames_Params_STRUCT_SIZE };
                RETURN_IF_NVPW_ERROR(false, NVPW_GetSupportedChipNames(&getSupportedChipNames));
                std::cout << "\n Number of supported chips : " << getSupportedChipNames.numChipNames;
                std::cout << "\n List of supported chips : \n";

                for (size_t i = 0; i < getSupportedChipNames.numChipNames; i++) {
                    std::cout << " " << getSupportedChipNames.ppChipNames[i] << "\n";
                }

                return true;
            }

            bool ListMetrics(const char* chipName, bool listSubMetrics) {

                NVPW_CUDA_MetricsContext_Create_Params metricsContextCreateParams = { NVPW_CUDA_MetricsContext_Create_Params_STRUCT_SIZE };
                metricsContextCreateParams.pChipName = chipName;
                RETURN_IF_NVPW_ERROR(false, NVPW_CUDA_MetricsContext_Create(&metricsContextCreateParams));

                NVPW_MetricsContext_Destroy_Params metricsContextDestroyParams = { NVPW_MetricsContext_Destroy_Params_STRUCT_SIZE };
                metricsContextDestroyParams.pMetricsContext = metricsContextCreateParams.pMetricsContext;
                SCOPE_EXIT([&]() { NVPW_MetricsContext_Destroy((NVPW_MetricsContext_Destroy_Params *)&metricsContextDestroyParams); });

                NVPW_MetricsContext_GetMetricNames_Begin_Params getMetricNameBeginParams = { NVPW_MetricsContext_GetMetricNames_Begin_Params_STRUCT_SIZE };
                getMetricNameBeginParams.pMetricsContext = metricsContextCreateParams.pMetricsContext;
                getMetricNameBeginParams.hidePeakSubMetrics = !listSubMetrics;
                getMetricNameBeginParams.hidePerCycleSubMetrics = !listSubMetrics;
                getMetricNameBeginParams.hidePctOfPeakSubMetrics = !listSubMetrics;
                RETURN_IF_NVPW_ERROR(false, NVPW_MetricsContext_GetMetricNames_Begin(&getMetricNameBeginParams));

                NVPW_MetricsContext_GetMetricNames_End_Params getMetricNameEndParams = { NVPW_MetricsContext_GetMetricNames_End_Params_STRUCT_SIZE };
                getMetricNameEndParams.pMetricsContext = metricsContextCreateParams.pMetricsContext;
                SCOPE_EXIT([&]() { NVPW_MetricsContext_GetMetricNames_End((NVPW_MetricsContext_GetMetricNames_End_Params *)&getMetricNameEndParams); });
                
                std::cout << getMetricNameBeginParams.numMetrics << " metrics in total on the chip\nMetrics List : \n";
                for (size_t i = 0; i < getMetricNameBeginParams.numMetrics; i++) {
                    std::cout << getMetricNameBeginParams.ppMetricNames[i] << "\n";
                }

                return true;
            }

            bool ListCounters(const char* chipName, bool listSubCounters){

                NVPW_CUDA_MetricsContext_Create_Params metricsContextCreateParams = { NVPW_CUDA_MetricsContext_Create_Params_STRUCT_SIZE };
                metricsContextCreateParams.pChipName = chipName;
                RETURN_IF_NVPW_ERROR(false, NVPW_CUDA_MetricsContext_Create(&metricsContextCreateParams));

                NVPW_MetricsContext_Destroy_Params metricsContextDestroyParams = { NVPW_MetricsContext_Destroy_Params_STRUCT_SIZE };
                metricsContextDestroyParams.pMetricsContext = metricsContextCreateParams.pMetricsContext;
                SCOPE_EXIT([&]() { NVPW_MetricsContext_Destroy((NVPW_MetricsContext_Destroy_Params *)&metricsContextDestroyParams); });

                NVPW_MetricsContext_GetCounterNames_Begin_Params getCounterNameBeginParams = { NVPW_MetricsContext_GetCounterNames_Begin_Params_STRUCT_SIZE };
                getCounterNameBeginParams.pMetricsContext = metricsContextCreateParams.pMetricsContext;
                RETURN_IF_NVPW_ERROR(false, NVPW_MetricsContext_GetCounterNames_Begin(&getCounterNameBeginParams));

                NVPW_MetricsContext_GetCounterNames_End_Params getCounterNameEndParams = { NVPW_MetricsContext_GetCounterNames_End_Params_STRUCT_SIZE };
                getCounterNameEndParams.pMetricsContext = metricsContextCreateParams.pMetricsContext;
                SCOPE_EXIT([&]() { NVPW_MetricsContext_GetCounterNames_End((NVPW_MetricsContext_GetCounterNames_End_Params *)&getCounterNameEndParams); });
                
                std::cout << getCounterNameBeginParams.numCounters << " counters in total on the chip\nCounters List : \n";
                for (size_t i = 0; i < getCounterNameBeginParams.numCounters; i++) {
                    std::cout << getCounterNameBeginParams.ppCounterNames[i] << "\n";
                }

                return true;
            }

            bool ListRatios(const char* chipName, bool listSubRatios) {

                NVPW_CUDA_MetricsContext_Create_Params metricsContextCreateParams = { NVPW_CUDA_MetricsContext_Create_Params_STRUCT_SIZE };
                metricsContextCreateParams.pChipName = chipName;
                RETURN_IF_NVPW_ERROR(false, NVPW_CUDA_MetricsContext_Create(&metricsContextCreateParams));

                NVPW_MetricsContext_Destroy_Params metricsContextDestroyParams = { NVPW_MetricsContext_Destroy_Params_STRUCT_SIZE };
                metricsContextDestroyParams.pMetricsContext = metricsContextCreateParams.pMetricsContext;
                SCOPE_EXIT([&]() { NVPW_MetricsContext_Destroy((NVPW_MetricsContext_Destroy_Params *)&metricsContextDestroyParams); });

                NVPW_MetricsContext_GetRatioNames_Begin_Params getRatioNameBeginParams = { NVPW_MetricsContext_GetRatioNames_Begin_Params_STRUCT_SIZE };
                getRatioNameBeginParams.pMetricsContext = metricsContextCreateParams.pMetricsContext;
                RETURN_IF_NVPW_ERROR(false, NVPW_MetricsContext_GetRatioNames_Begin(&getRatioNameBeginParams));

                NVPW_MetricsContext_GetRatioNames_End_Params getRatioNameEndParams = { NVPW_MetricsContext_GetRatioNames_End_Params_STRUCT_SIZE };
                getRatioNameEndParams.pMetricsContext = metricsContextCreateParams.pMetricsContext;
                SCOPE_EXIT([&]() { NVPW_MetricsContext_GetRatioNames_End((NVPW_MetricsContext_GetRatioNames_End_Params *)&getRatioNameEndParams); });
                
                std::cout << getRatioNameBeginParams.numRatios << " ratios in total on the chip\nRatios List : \n";
                for (size_t i = 0; i < getRatioNameBeginParams.numRatios; i++) {
                    std::cout << getRatioNameBeginParams.ppRatioNames[i] << "\n";
                }

                return true;
            }

            bool ListThroughputs(const char* chipName, bool listSubThroughputs) {

                NVPW_CUDA_MetricsContext_Create_Params metricsContextCreateParams = { NVPW_CUDA_MetricsContext_Create_Params_STRUCT_SIZE };
                metricsContextCreateParams.pChipName = chipName;
                RETURN_IF_NVPW_ERROR(false, NVPW_CUDA_MetricsContext_Create(&metricsContextCreateParams));

                NVPW_MetricsContext_Destroy_Params metricsContextDestroyParams = { NVPW_MetricsContext_Destroy_Params_STRUCT_SIZE };
                metricsContextDestroyParams.pMetricsContext = metricsContextCreateParams.pMetricsContext;
                SCOPE_EXIT([&]() { NVPW_MetricsContext_Destroy((NVPW_MetricsContext_Destroy_Params *)&metricsContextDestroyParams); });

                NVPW_MetricsContext_GetThroughputNames_Begin_Params getThroughputNamesBeginParams = { NVPW_MetricsContext_GetThroughputNames_Begin_Params_STRUCT_SIZE };
                getThroughputNamesBeginParams.pMetricsContext = metricsContextCreateParams.pMetricsContext;
                RETURN_IF_NVPW_ERROR(false, NVPW_MetricsContext_GetThroughputNames_Begin(&getThroughputNamesBeginParams));

                NVPW_MetricsContext_GetThroughputNames_End_Params getThroughputNamesEndParams = { NVPW_MetricsContext_GetThroughputNames_End_Params_STRUCT_SIZE };
                getThroughputNamesEndParams.pMetricsContext = metricsContextCreateParams.pMetricsContext;
                SCOPE_EXIT([&]() { NVPW_MetricsContext_GetThroughputNames_End((NVPW_MetricsContext_GetThroughputNames_End_Params *)&getThroughputNamesEndParams); });
                
                std::cout << getThroughputNamesBeginParams.numThroughputs << " throughputs in total on the chip\nThroughputs List : \n";
                for (size_t i = 0; i < getThroughputNamesBeginParams.numThroughputs; i++) {
                    std::cout << getThroughputNamesBeginParams.ppThroughputNames[i] << "\n";
                }

                return true;
            }

            bool ListThroughputBreakdowns(const char* chipName, const char* pThroughputName) {

                NVPW_CUDA_MetricsContext_Create_Params metricsContextCreateParams = { NVPW_CUDA_MetricsContext_Create_Params_STRUCT_SIZE };
                metricsContextCreateParams.pChipName = chipName;
                RETURN_IF_NVPW_ERROR(false, NVPW_CUDA_MetricsContext_Create(&metricsContextCreateParams));

                NVPW_MetricsContext_Destroy_Params metricsContextDestroyParams = { NVPW_MetricsContext_Destroy_Params_STRUCT_SIZE };
                metricsContextDestroyParams.pMetricsContext = metricsContextCreateParams.pMetricsContext;
                SCOPE_EXIT([&]() { NVPW_MetricsContext_Destroy((NVPW_MetricsContext_Destroy_Params *)&metricsContextDestroyParams); });

                NVPW_MetricsContext_GetThroughputBreakdown_Begin_Params getThroughputBreakdownBeginParams = { NVPW_MetricsContext_GetThroughputBreakdown_Begin_Params_STRUCT_SIZE };
                getThroughputBreakdownBeginParams.pMetricsContext = metricsContextCreateParams.pMetricsContext;
                getThroughputBreakdownBeginParams.pThroughputName = pThroughputName;
                RETURN_IF_NVPW_ERROR(false, NVPW_MetricsContext_GetThroughputBreakdown_Begin(&getThroughputBreakdownBeginParams));

                NVPW_MetricsContext_GetThroughputBreakdown_End_Params getThroughputBreakdownEndParams = { NVPW_MetricsContext_GetThroughputBreakdown_End_Params_STRUCT_SIZE };
                getThroughputBreakdownEndParams.pMetricsContext = metricsContextCreateParams.pMetricsContext;
                SCOPE_EXIT([&]() { NVPW_MetricsContext_GetThroughputBreakdown_End((NVPW_MetricsContext_GetThroughputBreakdown_End_Params *)&getThroughputBreakdownEndParams); });
                
                // std::cout << getThroughputBreakdownBeginParams.numMetrics << " throughputbreakdowns in total on the chip\nCounterNames List : \n";
                std::cout << "CounterNames List : \n";
                int i = -1;
                while(true){
                    ++i;
                    if(getThroughputBreakdownBeginParams.ppCounterNames[i]!=NULL){
                        std::cout << getThroughputBreakdownBeginParams.ppCounterNames[i] << "\n";
                    }else{
                        break;
                    }
                }
                std::cout << "\nSubThroughputNames List : " << std::endl;
                i = -1;
                while(true){
                    ++i;
                    if(getThroughputBreakdownBeginParams.ppSubThroughputNames[i]!=NULL){
                        std::cout << getThroughputBreakdownBeginParams.ppSubThroughputNames[i] << "\n";
                    }else{
                        break;
                    }
                }

                return true;
            }
        }
    }
}
