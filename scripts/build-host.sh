#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p build
c++ -std=c++17 -Wall -Wextra -Werror -Isrc -Iinclude src/control.cpp tests/control_test.cpp -o build/control-test
c++ -std=c++17 -Wall -Wextra -Werror -Isrc -Iinclude src/control.cpp src/telemetry.cpp simulator/main.cpp -o build/sapr-simulator
./build/control-test
