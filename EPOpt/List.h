#pragma once
namespace NV {
    namespace Metric {
        namespace Enum {
            // Function to print list of all supported chips
            bool ListSupportedChips();

            /* Function to print list of all metrics for a given chip
             * @param[in]  chipName         Chip Name for which metrics are to be listed
             * @param[in]  listSubMetrics   Whether submetrics(Peak, PerCycle, PctOfPeak) are to be listed or not
             */
            bool ListMetrics(const char* chipName, bool listSubMetrics);
            bool ListCounters(const char* chipName, bool listSubCounters);
            bool ListRatios(const char* chipName, bool listSubRatios);
            bool ListThroughputs(const char* chipName, bool listSubThroughputs);
            bool ListThroughputBreakdowns(const char* chipName, const char* pThroughputName);
        }
    }
}