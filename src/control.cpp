#include "control.hpp"
#include "profile.hpp"
#include <cmath>

namespace sapr {
const char* quality_name(Quality quality) {
    switch (quality) {
        case Quality::warmup: return "warmup";
        case Quality::ok: return "ok";
        case Quality::timeout: return "timeout";
        case Quality::crc: return "crc";
        case Quality::protocol: return "protocol";
        case Quality::range: return "range";
        case Quality::stale: return "stale";
    }
    return "unknown";
}

// CRC-8 and word framing adapted from AirCheck firmware/esp32/src/sensor_protocol.cpp.
bool decode_scd41_word(const uint8_t* bytes, uint16_t& value) {
    uint8_t crc = 0xff;
    for (int j = 0; j < 2; ++j) {
        crc ^= bytes[j];
        for (int bit = 0; bit < 8; ++bit) {
            crc = (crc & 0x80) ? (crc << 1) ^ 0x31 : crc << 1;
        }
    }
    if (crc != bytes[2]) return false;
    value = (uint16_t(bytes[0]) << 8) | bytes[1];
    return true;
}

bool decode_scd41(const uint8_t* bytes, std::size_t size, Reading& reading) {
    if (size != 9) return false;
    uint16_t words[3]{};
    for (std::size_t i = 0; i < 3; ++i) {
        if (!decode_scd41_word(bytes + 3 * i, words[i])) return false;
    }
    reading = {words[0], -45.0 + 175.0 * words[1] / 65535.0, 100.0 * words[2] / 65535.0};
    return true;
}

void Controller::read(uint64_t now, Reading reading) {
    if (reading.co2 < 250 || reading.co2 > 10000 ||
        !std::isfinite(reading.temperature) || reading.temperature < -60 || reading.temperature > 80 ||
        !std::isfinite(reading.humidity) || reading.humidity < 0 || reading.humidity > 100) {
        sensor_error(Quality::range);
        return;
    }
    state_.quality = Quality::ok;
    state_.has_reading = true;
    state_.reading = reading;
    state_.consecutive_failures = 0;
    last_good_at_ = now;
}

void Controller::sensor_error(Quality quality) {
    state_.quality = quality;
    ++state_.consecutive_failures;
}

void Controller::tick(uint64_t now, unsigned pulses, uint64_t window_ms) {
    if (state_.quality == Quality::ok && now - last_good_at_ >= stale_ms) {
        sensor_error(Quality::stale);
    }
    if (!commissioned_ || state_.quality != Quality::ok) {
        state_.fan_on = false;
        state_.rpm = -1;
        return;
    }
    if (state_.fan_on) {
        if (window_ms != 0) {
            const auto rpm = 60000ULL * pulses / (window_ms * pulses_per_revolution);
            if (rpm >= tach_min_rpm && rpm <= tach_max_rpm) {
                last_tach_at_ = now;
                state_.rpm = static_cast<int>(rpm);
            } else {
                state_.rpm = -1;
            }
        }
        if (now - last_tach_at_ >= tach_timeout_ms) state_.fan_fault = true;
        if (state_.fan_fault ||
            (state_.reading.co2 < off_below_ppm && now - enabled_at_ >= minimum_run_ms)) {
            state_.fan_on = false;
            state_.rpm = -1;
        }
        return;
    }
    if (!state_.fan_fault && state_.reading.co2 >= on_ppm) {
        enabled_at_ = last_tach_at_ = now;
        state_.fan_on = true;
    }
}

Snapshot Controller::snapshot(uint64_t now) const {
    Snapshot snapshot = state_;
    if (snapshot.has_reading) snapshot.age_ms = now - last_good_at_;
    return snapshot;
}
}
