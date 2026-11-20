#include "network.hpp"
#include "telemetry.hpp"

#include <algorithm>
#include <atomic>
#include <cstdio>
#include <string>

#include "esp_event.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_random.h"
#include "esp_sntp.h"
#include "esp_wifi.h"
#include "freertos/task.h"
#include "nvs.h"
#include "nvs_flash.h"

namespace sapr {
namespace {
constexpr char tag[] = "sapr-network";
std::atomic<bool> connected{false};
std::atomic<bool> synchronized{false};

struct Settings {
    std::string ssid, password, url, token, ntp_server, root_ca;
    bool network_ready = false;
};
Settings settings;

std::string read_string(nvs_handle_t handle, const char* key, std::size_t maximum) {
    std::size_t size = 0;
    if (nvs_get_str(handle, key, nullptr, &size) != ESP_OK || size < 2 || size > maximum + 1) return {};
    std::string value(size, '\0');
    if (nvs_get_str(handle, key, value.data(), &size) != ESP_OK) return {};
    value.resize(size - 1);
    return value;
}

void clock_updated(timeval*) { synchronized.store(true); }

void on_network_event(void*, esp_event_base_t base, int32_t id, void*) {
    if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) connected.store(true);
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) connected.store(false);
}

bool prepare_wifi() {
    if (esp_netif_init() != ESP_OK ||
        esp_event_loop_create_default() != ESP_OK || !esp_netif_create_default_wifi_sta()) return false;
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    if (esp_wifi_init(&init) != ESP_OK) return false;
    if (esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_network_event, nullptr) != ESP_OK ||
        esp_event_handler_register(WIFI_EVENT, WIFI_EVENT_STA_DISCONNECTED, on_network_event, nullptr) != ESP_OK) return false;
    wifi_config_t credentials{};
    std::copy(settings.ssid.begin(), settings.ssid.end(), credentials.sta.ssid);
    std::copy(settings.password.begin(), settings.password.end(), credentials.sta.password);
    credentials.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    return esp_wifi_set_storage(WIFI_STORAGE_RAM) == ESP_OK && esp_wifi_set_mode(WIFI_MODE_STA) == ESP_OK &&
           esp_wifi_set_config(WIFI_IF_STA, &credentials) == ESP_OK && esp_wifi_start() == ESP_OK;
}

bool post(const std::string& body) {
    esp_http_client_config_t options{};
    options.url = settings.url.c_str();
    options.cert_pem = settings.root_ca.c_str();
    options.timeout_ms = 3000;
    options.disable_auto_redirect = true;
    auto client = esp_http_client_init(&options);
    if (!client) return false;
    const std::string auth = "Bearer " + settings.token;
    esp_http_client_set_method(client, HTTP_METHOD_POST);
    esp_http_client_set_header(client, "Authorization", auth.c_str());
    esp_http_client_set_header(client, "X-AirCheck-Source", "real");
    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_post_field(client, body.data(), static_cast<int>(body.size()));
    const esp_err_t result = esp_http_client_perform(client);
    const int http_status = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);
    if (result != ESP_OK || (http_status != 200 && http_status != 201)) {
        ESP_LOGW(tag, "Telemetry send failed (%s, HTTP %d)", esp_err_to_name(result), http_status);
        return false;
    }
    return true;
}

void network_task(void* arg) {
    auto frames = static_cast<QueueHandle_t>(arg);
    if (prepare_wifi()) {
        esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);
        esp_sntp_setservername(0, settings.ntp_server.data());
        esp_sntp_set_time_sync_notification_cb(clock_updated);
        esp_sntp_init();
        uint8_t random[16]{};
        esp_fill_random(random, sizeof random);
        char boot_id[33]{};
        for (std::size_t i = 0; i < sizeof random; ++i) {
            std::snprintf(boot_id + 2 * i, 3, "%02x", static_cast<unsigned>(random[i]));
        }
        Frame frame{};
        std::string pending;
        uint64_t delivered = 0;
        for (;;) {
            const bool new_frame = xQueueReceive(frames, &frame, pdMS_TO_TICKS(2000)) == pdTRUE;
            if (!connected.load()) {
                esp_wifi_connect();
                pending.clear();
                vTaskDelay(pdMS_TO_TICKS(2000));
                continue;
            }
            if (new_frame && synchronized.load() && frame.epoch_ms > 0) {
                // Earlier snapshots without a confirmed delivery were superseded by a newer snapshot.
                frame.dropped_packets = frame.sequence - delivered;
                pending = telemetry_json(frame, boot_id, Source::real);
            }
            if (!pending.empty() && post(pending)) {
                ++delivered;
                pending.clear();
            }
        }
    }
    ESP_LOGE(tag, "Wi-Fi setup failed. Local regulation remains active.");
    vTaskDelete(nullptr);
}
}

bool load_board_config() {
    nvs_handle_t handle = 0;
    if (nvs_flash_init() != ESP_OK || nvs_open("sapr", NVS_READONLY, &handle) != ESP_OK) return false;
    uint8_t version = 0;
    uint8_t commissioned = 0;
    if (nvs_get_u8(handle, "version", &version) == ESP_OK && version == 1) {
        nvs_get_u8(handle, "commissioned", &commissioned);
        settings.ssid = read_string(handle, "ssid", 32);
        settings.password = read_string(handle, "password", 64);
        settings.url = read_string(handle, "url", 255);
        settings.token = read_string(handle, "token", 256);
        settings.ntp_server = read_string(handle, "ntp_server", 253);
        settings.root_ca = read_string(handle, "root_ca", 3900);
        settings.network_ready = !settings.ssid.empty() && settings.password.size() >= 8 &&
            settings.url.rfind("https://", 0) == 0 && settings.token.size() >= 32 &&
            std::all_of(settings.token.begin(), settings.token.end(), [](unsigned char c) { return c >= 33 && c <= 126; }) &&
            !settings.ntp_server.empty() && !settings.root_ca.empty();
    }
    nvs_close(handle);
    return commissioned == 1;
}

void start_network(QueueHandle_t frames) {
    if (frames && settings.network_ready) {
        if (xTaskCreate(network_task, "sapr-net", 10240, frames, 3, nullptr) != pdPASS) {
            ESP_LOGE(tag, "Unable to start telemetry task");
        }
    } else {
        ESP_LOGI(tag, "Using local mode; load a SAPR NVS configuration to enable telemetry.");
    }
}
}
