#ifndef CONSTANTS_H
#define CONSTANTS_H

// using higher than 15MHz for both timer and serial math
#define RUN_HZ           20971520

// Motor interrupt rate and other info
#define MOTOR_CONTROL_RATE          20000u
#define MOTOR_CONTROL_RATE_HZ       MOTOR_CONTROL_RATE
#define NUM_MOTORS                  4u
#define MOTOR_STREAM_BUFFER_FRAMES  128u
#define MOTOR_STREAM_START_FRAMES   32u

// UART baud rate to use with the sender
#define SERIAL_BAUD_RATE            230400u

#endif
