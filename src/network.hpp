#pragma once
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

namespace sapr {
void start_network(QueueHandle_t frames);
}
