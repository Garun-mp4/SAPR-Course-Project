#include "telemetry.hpp"
#include "profile.hpp"
#include <cstdio>
#include <ctime>
#include <iomanip>
#include <locale>
#include <sstream>

namespace sapr {
namespace {
std::string timestamp(int64_t epoch_ms) {
    if (epoch_ms <= 0) return "null";
    auto seconds = static_cast<std::time_t>(epoch_ms / 1000);
    std::tm utc{};
#ifdef _WIN32
    if (gmtime_s(&utc, &seconds) != 0) return "null";
#else
    if (!gmtime_r(&seconds, &utc)) return "null";
#endif
    char date[30]{};
    std::strftime(date, sizeof date, "%Y-%m-%dT%H:%M:%S", &utc);
    char fraction[8]{};
    std::snprintf(fraction, sizeof fraction, ".%03uZ", unsigned(epoch_ms % 1000));
    return "\"" + std::string(date) + fraction + "\"";
}
}

std::string telemetry_json(const Frame& frame, const std::string& boot_id, Source source) {
    const auto& s = frame.snapshot;
    const char* status = quality_name(s.quality);
    std::ostringstream out;
    out.imbue(std::locale::classic());
    out << std::boolalpha << std::setprecision(8)
        << R"({"schema_version":2,"device_id":")" << device_id
        << R"(","boot_id":")" << boot_id << R"(","data_source":")"
        << (source == Source::real ? "real" : "simulator")
        << R"(","sequence":)" << frame.sequence
        << R"(,"sampled_at":)" << timestamp(frame.epoch_ms)
        << R"(,"sensors":[{"sensor_id":"indoor_climate","status":")" << status
        << R"(","reason":")" << status
        << R"(","last_good_at":)" << timestamp(s.has_reading && frame.epoch_ms > 0 ?
                                               frame.epoch_ms - static_cast<int64_t>(s.age_ms) : 0)
        << R"(,"age_ms":)" << s.age_ms
        << R"(,"consecutive_failures":)" << s.consecutive_failures << R"(,"values":{)";
    if (s.has_reading) {
        out << R"("co2":)" << s.reading.co2 << R"(,"temperature":)" << s.reading.temperature
            << R"(,"humidity":)" << s.reading.humidity;
    } else {
        out << R"("co2":null,"temperature":null,"humidity":null)";
    }
    out << R"(}},{"sensor_id":"outdoor_climate","status":"unknown","reason":"not_installed","last_good_at":null,"age_ms":0,"consecutive_failures":0,"values":{"temperature":null,"humidity":null}},)"
        << R"({"sensor_id":"indoor_particles","status":"unknown","reason":"not_installed","last_good_at":null,"age_ms":0,"consecutive_failures":0,"values":{"pm25":null}},)"
        << R"({"sensor_id":"outdoor_particles","status":"unknown","reason":"not_installed","last_good_at":null,"age_ms":0,"consecutive_failures":0,"values":{"pm25":null}}],)"
        << R"("controller":{"uptime_ms":)" << frame.uptime_ms
        << R"(,"reset_reason":null,"firmware_version":"sapr-2.0.0","free_heap":null,"minimum_free_heap":null,"clock_synced":)"
        << (frame.epoch_ms > 0) << R"(,"outputs_commissioned":)" << frame.outputs_commissioned
        << R"(,"dropped_packets":)" << frame.dropped_packets << R"(,"queue_depth":0},"actuators":{)"
        << R"("window":{"open_limit":false,"close_limit":false,"position_percent":null,"position_quality":"unknown","motion":"stopped"},)"
        << R"("intake":{"requested_on":false,"rpm":null,"status":"unknown"},"exhaust":{"requested_on":)"
        << s.fan_on << R"(,"rpm":)";
    if (s.rpm >= 0) out << s.rpm; else out << "null";
    out << R"(,"status":")" << (s.fan_fault ? "fault" : s.rpm >= 0 ? "measured" : "unknown")
        << R"("}},"command_results":[]})";
    return out.str();
}
}
