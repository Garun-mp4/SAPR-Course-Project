#pragma once
#include "control.hpp"
#include <cstdint>
#include <string>

namespace sapr {
enum class Source { real, simulator };

struct Frame {
    Snapshot snapshot;
    uint64_t uptime_ms;
    uint64_t sequence;
    int64_t epoch_ms;
};

std::string telemetry_json(const Frame& frame, const std::string& boot_id, Source source);
}
