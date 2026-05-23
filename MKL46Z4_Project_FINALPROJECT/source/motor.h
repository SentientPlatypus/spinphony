#ifndef MOTOR_H
#define MOTOR_H

#include <stdint.h>
#include "constants.h"

// Individual song frame data
typedef struct {
    uint16_t duration;
    uint32_t speed[NUM_MOTORS];
} MotorStreamFrame;

// Motor functions used by app and serial parser
void Motor_Init(void);
void Motor_StartTimer(void);
uint8_t Motor_StreamPush(const MotorStreamFrame *frame);

#endif
