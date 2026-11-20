idf_component_register(
    SRCS "main.cpp" "network.cpp" "control.cpp" "telemetry.cpp"
    INCLUDE_DIRS "." "../include"
    REQUIRES esp_driver_gpio esp_driver_i2c esp_driver_pcnt esp_timer
             esp_http_client esp_wifi esp_event esp_netif lwip nvs_flash
)
