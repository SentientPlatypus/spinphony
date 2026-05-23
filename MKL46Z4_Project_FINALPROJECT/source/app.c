#include <pin_mux.h>
#include <clock_config.h>
#include <board.h>

#include "motor.h"
#include "serial_stream.h"

void App_init(void) {
    // first init board at custom rate and motor and serial
    BOARD_InitBootPins();
    BOARD_InitBootClocks();
    BOARD_InitDebugConsole();
    Motor_Init();
    SerialStream_Init();

    // Start stepping after the hardware and serial input are ready
    Motor_StartTimer();
}

void App_run(void) {
    // Main loop keeps checking serial, motors interrupt this
    while (1) {
        SerialStream_Service();
    }
}
