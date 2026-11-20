#include "control.hpp"
#include "network.hpp"
#include "profile.hpp"
#include "telemetry.hpp"

#include <sys/time.h>
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "driver/pulse_cnt.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/task.h"

namespace sapr {
namespace {
constexpr char tag[] = "sapr-control";
constexpr gpio_num_t fan = static_cast<gpio_num_t>(enable_gpio);
constexpr TickType_t control_step = pdMS_TO_TICKS(50);

uint64_t monotonic_ms() { return esp_timer_get_time() / 1000; }

int64_t epoch_ms() {
    timeval now{};
    gettimeofday(&now, nullptr);
    return now.tv_sec >= 1700000000 ? int64_t(now.tv_sec) * 1000 + now.tv_usec / 1000 : 0;
}

i2c_master_dev_handle_t sensor_init() {
    i2c_master_bus_config_t bus_config{};
    bus_config.i2c_port = I2C_NUM_0;
    bus_config.sda_io_num = static_cast<gpio_num_t>(sda_gpio);
    bus_config.scl_io_num = static_cast<gpio_num_t>(scl_gpio);
    bus_config.clk_source = I2C_CLK_SRC_DEFAULT;
    bus_config.glitch_ignore_cnt = 7;
    i2c_master_bus_handle_t bus = nullptr;
    if (i2c_new_master_bus(&bus_config, &bus) != ESP_OK) return nullptr;
    i2c_device_config_t config{};
    config.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    config.device_address = sensor_address;
    config.scl_speed_hz = i2c_hz;
    i2c_master_dev_handle_t device = nullptr;
    if (i2c_master_bus_add_device(bus, &config, &device) != ESP_OK) return nullptr;
    return device;
}

bool send_command(i2c_master_dev_handle_t device, uint16_t command) {
    const uint8_t bytes[] = {static_cast<uint8_t>(command >> 8), static_cast<uint8_t>(command)};
    return i2c_master_transmit(device, bytes, sizeof bytes, 30) == ESP_OK;
}

struct SensorSession {
    bool started = false;
    uint64_t last_ready = 0;
};

void restart_sensor(i2c_master_dev_handle_t device, SensorSession& session) {
    send_command(device, 0x3f86);
    // The next scheduled poll is at least 1000 ms later. STOP needs 500 ms.
    session.started = false;
}

void scd41_sample(i2c_master_dev_handle_t device, Controller& controller, SensorSession& session) {
    if (!device) {
        controller.sensor_error(Quality::protocol);
        return;
    }
    if (!session.started) {
        session.started = send_command(device, 0x21b1);
        session.last_ready = monotonic_ms();
        if (!session.started) {
            controller.sensor_error(Quality::timeout);
            restart_sensor(device, session);
        }
        return;
    }
    // SCD4x command timing and CRC framing follow the SCD41 portion of AirCheck's driver.
    uint8_t status_bytes[3]{};
    if (!send_command(device, 0xe4b8)) {
        controller.sensor_error(Quality::timeout);
        restart_sensor(device, session);
        return;
    }
    vTaskDelay(pdMS_TO_TICKS(20));
    uint16_t status = 0;
    if (i2c_master_receive(device, status_bytes, sizeof status_bytes, 30) != ESP_OK) {
        controller.sensor_error(Quality::timeout);
        restart_sensor(device, session);
        return;
    }
    if (!decode_scd41_word(status_bytes, status)) {
        controller.sensor_error(Quality::crc);
        return;
    }
    if ((status & 0x07ff) == 0) {
        if (monotonic_ms() - session.last_ready >= stale_ms) {
            controller.sensor_error(Quality::stale);
            restart_sensor(device, session);
        }
        return;
    }
    session.last_ready = monotonic_ms();
    if (!send_command(device, 0xec05)) {
        controller.sensor_error(Quality::timeout);
        restart_sensor(device, session);
        return;
    }
    vTaskDelay(pdMS_TO_TICKS(20));
    uint8_t bytes[9]{};
    Reading reading{};
    if (i2c_master_receive(device, bytes, sizeof bytes, 30) != ESP_OK) {
        controller.sensor_error(Quality::timeout);
        restart_sensor(device, session);
    } else if (!decode_scd41(bytes, sizeof bytes, reading)) {
        controller.sensor_error(Quality::crc);
    } else {
        controller.read(monotonic_ms(), reading);
    }
}

pcnt_unit_handle_t tach_init() {
    pcnt_unit_config_t config{};
    config.high_limit = 30000;
    config.low_limit = -1;
    config.flags.accum_count = true;
    pcnt_unit_handle_t unit = nullptr;
    if (pcnt_new_unit(&config, &unit) != ESP_OK) return nullptr;
    pcnt_chan_config_t channel_config{};
    channel_config.edge_gpio_num = tach_gpio;
    channel_config.level_gpio_num = -1;
    pcnt_channel_handle_t channel = nullptr;
    pcnt_glitch_filter_config_t filter{};
    filter.max_glitch_ns = 1000;
    if (pcnt_new_channel(unit, &channel_config, &channel) != ESP_OK ||
        pcnt_channel_set_edge_action(channel, PCNT_CHANNEL_EDGE_ACTION_INCREASE, PCNT_CHANNEL_EDGE_ACTION_HOLD) != ESP_OK ||
        pcnt_unit_set_glitch_filter(unit, &filter) != ESP_OK ||
        pcnt_unit_add_watch_point(unit, config.high_limit) != ESP_OK ||
        pcnt_unit_add_watch_point(unit, config.low_limit) != ESP_OK ||
        pcnt_unit_enable(unit) != ESP_OK || pcnt_unit_clear_count(unit) != ESP_OK ||
        pcnt_unit_start(unit) != ESP_OK) return nullptr;
    return unit;
}
}
}

extern "C" void app_main() {
    using namespace sapr;
    gpio_set_level(fan, 0);
    if (gpio_set_direction(fan, GPIO_MODE_OUTPUT) != ESP_OK) return;
    auto tach = tach_init();
    auto sensor = sensor_init();
    const bool enabled = load_board_config() && tach && sensor;
    if (!enabled) ESP_LOGW(tag, "Actuator locked: check commissioning, tachometer and sensor interface.");
    if (sensor) {
        send_command(sensor, 0x3f86);
        vTaskDelay(pdMS_TO_TICKS(550));
    }
    SensorSession sensor_session{sensor && send_command(sensor, 0x21b1), monotonic_ms()};
    auto frames = xQueueCreate(1, sizeof(Frame));
    start_network(frames);
    Controller controller(enabled);
    uint64_t sequence = 0;
    uint32_t last_count = 0;
    bool fan_on = false;
    uint64_t last_window = monotonic_ms();
    uint64_t next_sample = last_window + 1000;
    uint64_t next_frame = last_window;
    for (;;) {
        const auto before_sample = monotonic_ms();
        if (before_sample >= next_sample) {
            scd41_sample(sensor, controller, sensor_session);
            next_sample = before_sample + 1000;
        }
        const auto now = monotonic_ms();
        unsigned pulses = 0;
        uint64_t window_ms = 0;
        if (tach && now - last_window >= 1000) {
            int count = 0;
            if (pcnt_unit_get_count(tach, &count) == ESP_OK) {
                window_ms = now - last_window;
                pulses = static_cast<uint32_t>(count) - last_count;
                last_count = static_cast<uint32_t>(count);
                last_window = now;
            }
        }
        controller.tick(now, pulses, window_ms);
        const auto snapshot = controller.snapshot(now);
        if (snapshot.fan_on != fan_on) {
            int count = 0;
            if (tach && pcnt_unit_get_count(tach, &count) == ESP_OK) {
                last_count = static_cast<uint32_t>(count);
                last_window = now;
            }
            fan_on = snapshot.fan_on;
            gpio_set_level(fan, fan_on);
        }
        if (now >= next_frame) {
            if (frames) {
                const Frame frame{snapshot, now, sequence++, epoch_ms(), enabled};
                xQueueOverwrite(frames, &frame);
            }
            ESP_LOGI(tag, "CO2=%d, %s, fan=%s, rpm=%d%s", snapshot.has_reading ? snapshot.reading.co2 : -1,
                     quality_name(snapshot.quality), snapshot.fan_on ? "on" : "off",
                     snapshot.rpm, snapshot.fan_fault ? ", tach fault" : "");
            next_frame = now + sample_period_ms;
        }
        vTaskDelay(control_step);
    }
}
