#include "network.hpp"
#include "telemetry.hpp"

#include <array>
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
#include "nvs_flash.h"

#if __has_include("network_config.hpp")
#include "network_config.hpp"
#else
#include "network_config.example.hpp"
#endif

namespace sapr {
namespace {
constexpr char tag[] = "sapr-network";
std::atomic<bool> connected{false};
std::atomic<bool> synchronized{false};

void clock_updated(timeval*) { synchronized.store(true); }

void on_network_event(void*, esp_event_base_t base, int32_t id, void*) {
    if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) connected.store(true);
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) connected.store(false);
}

bool prepare_wifi() {
    if (nvs_flash_init() != ESP_OK || esp_netif_init() != ESP_OK ||
        esp_event_loop_create_default() != ESP_OK || !esp_netif_create_default_wifi_sta()) return false;
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    if (esp_wifi_init(&init) != ESP_OK) return false;
    if (esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_network_event, nullptr) != ESP_OK ||
        esp_event_handler_register(WIFI_EVENT, WIFI_EVENT_STA_DISCONNECTED, on_network_event, nullptr) != ESP_OK) return false;
    wifi_config_t credentials{};
    snprintf(reinterpret_cast<char*>(credentials.sta.ssid), sizeof credentials.sta.ssid, "%s", config::ssid);
    snprintf(reinterpret_cast<char*>(credentials.sta.password), sizeof credentials.sta.password, "%s", config::password);
    credentials.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    return esp_wifi_set_storage(WIFI_STORAGE_RAM) == ESP_OK && esp_wifi_set_mode(WIFI_MODE_STA) == ESP_OK &&
           esp_wifi_set_config(WIFI_IF_STA, &credentials) == ESP_OK && esp_wifi_start() == ESP_OK;
}

bool post(const std::string& body) {
    esp_http_client_config_t options{};
    options.url = config::telemetry_url;
    options.cert_pem = config::root_ca;
    options.timeout_ms = 3000;
    options.disable_auto_redirect = true;
    auto client = esp_http_client_init(&options);
    if (!client) return false;
    const std::string auth = std::string("Bearer ") + config::token;
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
        esp_sntp_setservername(0, const_cast<char*>(config::sntp_server));
        esp_sntp_set_time_sync_notification_cb(clock_updated);
        esp_sntp_init();
        const uint32_t first = esp_random();
        const uint32_t second = esp_random();
        char boot_id[24]{};
        snprintf(boot_id, sizeof boot_id, "%08lx%08lx", static_cast<unsigned long>(first),
                 static_cast<unsigned long>(second));
        Frame frame{};
        std::string pending;
        for (;;) {
            const bool new_frame = xQueueReceive(frames, &frame, pdMS_TO_TICKS(2000)) == pdTRUE;
            if (!connected.load()) {
                esp_wifi_connect();
                pending.clear();
                vTaskDelay(pdMS_TO_TICKS(2000));
                continue;
            }
            if (new_frame && synchronized.load() && frame.epoch_ms > 0) {
                pending = telemetry_json(frame, boot_id, Source::real);
            }
            if (!pending.empty() && post(pending)) pending.clear();
        }
    }
    ESP_LOGE(tag, "Wi-Fi setup failed. Local regulation remains active.");
    vTaskDelete(nullptr);
}
}

void start_network(QueueHandle_t frames) {
    if (frames && config::ssid[0] && sizeof config::token >= 33 && config::root_ca[0] &&
        sizeof config::ssid <= 33 && sizeof config::password >= 9 && sizeof config::password <= 64 &&
        std::string(config::telemetry_url).rfind("https://", 0) == 0) {
        if (xTaskCreate(network_task, "sapr-net", 10240, frames, 3, nullptr) != pdPASS) {
            ESP_LOGE(tag, "Unable to start telemetry task");
        }
    } else {
        ESP_LOGI(tag, "Using local regulation; set network_config.hpp to enable telemetry.");
    }
}
}
