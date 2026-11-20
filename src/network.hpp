#pragma once
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

namespace sapr {
bool load_board_config();
void start_network(QueueHandle_t frames);
}
