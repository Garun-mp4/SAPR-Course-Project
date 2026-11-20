#pragma once
#include <cstdint>

namespace sapr {
inline constexpr char device_id[] = "sapr-room-01";
inline constexpr int sda_gpio = 21;
inline constexpr int scl_gpio = 22;
inline constexpr int i2c_hz = 100000;
inline constexpr int sensor_address = 0x62;
inline constexpr int enable_gpio = 25;
inline constexpr int tach_gpio = 36;
inline constexpr int pulses_per_revolution = 2;
inline constexpr int tach_min_rpm = 200;
inline constexpr int tach_max_rpm = 2500;
inline constexpr int on_ppm = 1000;
inline constexpr int off_below_ppm = 800;
inline constexpr uint64_t minimum_run_ms = 300000;
inline constexpr uint64_t sample_period_ms = 5000;
inline constexpr uint64_t stale_ms = 15000;
inline constexpr uint64_t tach_timeout_ms = 5000;
}
