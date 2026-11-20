#include "control.hpp"
#include "profile.hpp"
#include <cstdlib>
#include <iostream>

using namespace sapr;

void check(bool condition, const char* explanation) {
    if (!condition) {
        std::cerr << explanation << '\n';
        std::exit(1);
    }
}

int main() {
    Controller uncommissioned;
    uncommissioned.read(0, {1200, 22.5, 45});
    uncommissioned.tick(0, 0, 0);
    check(!uncommissioned.snapshot(0).fan_on, "A valid reading cannot commission the output");
    Controller controller(true);
    controller.tick(0, 0, 0);
    check(!controller.snapshot(0).fan_on, "Warmup must keep fan off");
    controller.read(1, {999, 22.5, 45});
    controller.tick(1, 0, 0);
    check(!controller.snapshot(1).fan_on, "999 ppm cannot start the fan");
    controller.read(2, {1000, 22.5, 45});
    controller.tick(2, 0, 0);
    check(controller.snapshot(2).fan_on, "1000 ppm must start the fan");
    check(controller.snapshot(2).rpm == -1, "An output request cannot be reported as rotation");
    for (uint64_t now = 1002; now <= 300002; now += 1000) {
        controller.read(now, {now < 150002 ? 750 : 800, 22.5, 45});
        controller.tick(now, 60, 1000);
        check(controller.snapshot(now).fan_on, "Minimum runtime and 800 ppm boundary must both hold");
        check(controller.snapshot(now).rpm == 1800, "60 pulses per second must equal 1800 RPM");
    }
    controller.read(301002, {799, 22.5, 45});
    controller.tick(301002, 60, 1000);
    check(!controller.snapshot(301002).fan_on, "799 ppm must stop a fan after minimum runtime");

    Controller sensor(true);
    sensor.read(0, {1050, 22, 45});
    sensor.tick(0, 0, 0);
    for (uint64_t now = 1000; now <= stale_ms; now += 1000) sensor.tick(now, 60, 1000);
    check(sensor.snapshot(stale_ms).quality == Quality::stale && !sensor.snapshot(stale_ms).fan_on,
          "Stale sensor must stop ventilation at the age limit");
    sensor.read(16000, {1050, 22, 45});
    sensor.tick(16000, 0, 0);
    sensor.sensor_error(Quality::crc);
    sensor.tick(16050, 0, 0);
    const auto failed = sensor.snapshot(16050);
    check(!failed.fan_on && failed.has_reading && failed.reading.co2 == 1050 &&
          failed.age_ms == 50 && failed.consecutive_failures == 1,
          "Invalid data must stop the fan and preserve the previous sample's age");
    sensor.read(20000, {900, 22, 45});
    sensor.tick(20000, 0, 0);
    check(!sensor.snapshot(20000).fan_on, "Recovery inside the hysteresis band must stay off");
    sensor.read(25000, {0, 22, 45});
    check(sensor.snapshot(25000).quality == Quality::range, "Invalid CO2 must be rejected");

    Controller tach(true);
    tach.read(0, {1050, 22, 45});
    tach.tick(0, 0, 0);
    tach.tick(tach_timeout_ms - 1, 1200, 1000);
    check(tach.snapshot(tach_timeout_ms - 1).fan_on, "Startup grace must be available");
    check(tach.snapshot(tach_timeout_ms - 1).rpm == -1, "Glitches cannot confirm rotation");
    tach.tick(tach_timeout_ms, 0, 1000);
    check(tach.snapshot(tach_timeout_ms).fan_fault && !tach.snapshot(tach_timeout_ms).fan_on,
          "Missing tachometer pulses must latch a fault");
    tach.read(6000, {1100, 22, 45});
    tach.tick(6000, 0, 1000);
    check(!tach.snapshot(6000).fan_on, "A new CO2 reading cannot clear a latched fan fault");

    const uint8_t raw[] = {0xbe, 0xef, 0x92, 0xbe, 0xef, 0x92, 0xbe, 0xef, 0x92};
    Reading sample{};
    check(decode_scd41(raw, sizeof raw, sample) && sample.co2 == 0xbeef,
          "SCD41 frame must decode valid Sensirion CRC-8 words");
    const uint8_t invalid[] = {0xbe, 0xee, 0x92, 0xbe, 0xef, 0x92, 0xbe, 0xef, 0x92};
    check(!decode_scd41(invalid, sizeof invalid, sample), "Corrupt frames must fail CRC");
    std::cout << "PASS threshold, hysteresis, hold time, timeout, sensor recovery, tach and CRC\n";
}
