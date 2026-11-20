#pragma once
#include <cstddef>
#include <cstdint>

namespace sapr {
enum class Quality { warmup, ok, timeout, crc, protocol, range, stale };
const char* quality_name(Quality quality);

struct Reading {
    int co2;
    double temperature;
    double humidity;
};

struct Snapshot {
    Quality quality = Quality::warmup;
    bool has_reading = false;
    Reading reading{};
    uint64_t age_ms = 0;
    unsigned consecutive_failures = 0;
    bool fan_on = false;
    bool fan_fault = false;
    int rpm = -1;
};

bool decode_scd41(const uint8_t* bytes, std::size_t size, Reading& reading);
bool decode_scd41_word(const uint8_t* bytes, uint16_t& value);

class Controller {
public:
    void read(uint64_t now, Reading reading);
    void sensor_error(Quality quality);
    void tick(uint64_t now, unsigned pulses, uint64_t window_ms);
    Snapshot snapshot(uint64_t now) const;

private:
    Snapshot state_{};
    uint64_t last_good_at_ = 0;
    uint64_t enabled_at_ = 0;
    uint64_t last_tach_at_ = 0;
};
}
