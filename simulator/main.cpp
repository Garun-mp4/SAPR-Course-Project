#include "control.hpp"
#include "profile.hpp"
#include "telemetry.hpp"

#include <chrono>
#include <iostream>
#include <random>
#include <string>

using namespace sapr;

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "Usage: sapr-simulator normal|sensor|tach|network\n";
        return 2;
    }
    const std::string scenario = argv[1];
    if (scenario != "normal" && scenario != "sensor" && scenario != "tach" && scenario != "network") {
        std::cerr << "Unknown scenario\n";
        return 2;
    }

    std::random_device random;
    const std::string boot = "sapr-sim-" + std::to_string(random()) + "-" + std::to_string(random());
    const auto epoch = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    Controller controller(true);  // Enables the virtual output, never the physical one.
    uint64_t sequence = 0;
    for (uint64_t now = 0; now <= 305000; now += 1000) {
        const int ppm = now < 5000 ? 700 : now < 10000 ? 1050 : now < 15000 ? 900 : 750;
        if (now % sample_period_ms == 0) {
            if (scenario == "sensor" && now == 10000) controller.sensor_error(Quality::timeout);
            else controller.read(now, {ppm, 22.5, 45.0});
        }
        const auto previous = controller.snapshot(now);
        const unsigned pulses = previous.fan_on && scenario != "tach" ? 60 : 0;
        controller.tick(now, pulses, 1000);

        if (now == 0 || now == 5000 || now == 6000 || now == 10000 ||
            now == 15000 || now == 304000 || now == 305000) {
            const auto current = controller.snapshot(now);
            // Keep the local trace on one virtual UTC timeline. The demo maps it to a short wire timeline.
            std::cout << telemetry_json({current, now, sequence++, epoch - 305000 + static_cast<int64_t>(now)},
                                        boot, Source::simulator) << '\n';
        }
    }
}
