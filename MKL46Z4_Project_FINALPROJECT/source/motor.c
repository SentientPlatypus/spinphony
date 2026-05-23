#include "motor.h"

#include "MKL46Z4.h"

#define STEP0_BIT 16u
#define STEP1_BIT 17u
#define STEP2_BIT 18u
#define STEP3_BIT 19u
#define STEP_MASK ((1u << STEP0_BIT) | (1u << STEP1_BIT) | (1u << STEP2_BIT) | (1u << STEP3_BIT))
#define ENABLE0_BIT 20u
#define ENABLE1_BIT 21u
#define ENABLE2_BIT 22u
#define ENABLE3_BIT 23u
#define ENABLE_MASK ((1u << ENABLE0_BIT) | (1u << ENABLE1_BIT) | (1u << ENABLE2_BIT) | (1u << ENABLE3_BIT))
#define MOTOR_PIT_CHANNEL 0u

// Live motor state read by the interrupt
static volatile uint32_t phase[NUM_MOTORS];
static volatile uint32_t speed[NUM_MOTORS];
static volatile uint8_t stepHigh[NUM_MOTORS];

/* Queue is circular buffer of motor commands */
static volatile uint16_t ticksLeft = 0u;
static volatile uint8_t writePos = 0u;
static volatile uint8_t readPos = 0u;
static volatile uint8_t framesQueued = 0u;
static volatile uint8_t streamReady = 0u;
static MotorStreamFrame frameQueue[MOTOR_STREAM_BUFFER_FRAMES];

static uint32_t enable_mask_for_motor(uint8_t motor) {
    /* STEP pins PTE19-PTE16, respectively to EN pins PTE20-PTE23 */
    return (1u << (ENABLE3_BIT - motor));
}

static void enable_set(uint8_t motor, uint8_t enabled) {
    uint32_t mask = enable_mask_for_motor(motor);
    // using Active-Low EN logic
    if (enabled) {
        GPIOE->PCOR = mask;
    } else {
        GPIOE->PSOR = mask;
    }
}

static void enable_all_set(uint8_t enabled) {
    // using Active-Low EN Logic
    if (enabled) {
        GPIOE->PCOR = ENABLE_MASK;
    } else {
        GPIOE->PSOR = ENABLE_MASK;
    }
}

static void step_set(uint8_t motor, uint8_t high) {
    uint32_t bit = STEP0_BIT + motor;
    if (high) {
        GPIOE->PSOR = (1u << bit);
    } else {
        GPIOE->PCOR = (1u << bit);
    }
}

static void set_all_increments(uint32_t value) {
    uint32_t motor;
    for (motor = 0; motor < NUM_MOTORS; motor++) {
        speed[motor] = value;
        enable_set((uint8_t)motor, (uint8_t)(value != 0u));
    }
}

static void load_stream_frame(void) {
    uint32_t motor;

    // stop stepping if no frames left
    if (framesQueued == 0u) {
        set_all_increments(0u);
        streamReady = 0u;
        return;
    }

    // Wait for a good amount of frames to start stepping
    if (!streamReady && framesQueued < MOTOR_STREAM_START_FRAMES) {
        set_all_increments(0u);
        return;
    }

    streamReady = 1u;
    for (motor = 0; motor < NUM_MOTORS; motor++) {
        speed[motor] = frameQueue[readPos].speed[motor];
        enable_set((uint8_t)motor, (uint8_t)(speed[motor] != 0u));
    }

    ticksLeft = frameQueue[readPos].duration;
    if (ticksLeft == 0u) {
        ticksLeft = 1u;
    }

    readPos++;
    if (readPos >= MOTOR_STREAM_BUFFER_FRAMES) {
        readPos = 0u;
    }
    framesQueued--;
}

void Motor_Init(void) {
    uint32_t motor;

    // PORTE for pins, PIT for motor timer.
    SIM->SCGC5 |= SIM_SCGC5_PORTE_MASK;
    SIM->SCGC6 |= SIM_SCGC6_PIT_MASK;

    // STEP and EN GPIO pins.
    PORTE->PCR[STEP0_BIT] = PORT_PCR_MUX(1u);
    PORTE->PCR[STEP1_BIT] = PORT_PCR_MUX(1u);
    PORTE->PCR[STEP2_BIT] = PORT_PCR_MUX(1u);
    PORTE->PCR[STEP3_BIT] = PORT_PCR_MUX(1u);
    PORTE->PCR[ENABLE0_BIT] = PORT_PCR_MUX(1u);
    PORTE->PCR[ENABLE1_BIT] = PORT_PCR_MUX(1u);
    PORTE->PCR[ENABLE2_BIT] = PORT_PCR_MUX(1u);
    PORTE->PCR[ENABLE3_BIT] = PORT_PCR_MUX(1u);

    GPIOE->PDDR |= STEP_MASK | ENABLE_MASK;
    GPIOE->PCOR = STEP_MASK;
    enable_all_set(0u);

    for (motor = 0; motor < NUM_MOTORS; motor++) {
        phase[motor] = 0u;
        speed[motor] = 0u;
        stepHigh[motor] = 0u;
    }

    ticksLeft = 0u;
    writePos = 0u;
    readPos = 0u;
    framesQueued = 0u;
    streamReady = 0u;

    // PIT for 20khz motor update
    PIT->MCR = 0u;
    PIT->CHANNEL[MOTOR_PIT_CHANNEL].TCTRL = 0u;
    PIT->CHANNEL[MOTOR_PIT_CHANNEL].LDVAL =
        (uint32_t)((RUN_HZ / MOTOR_CONTROL_RATE_HZ) - 1u);
    PIT->CHANNEL[MOTOR_PIT_CHANNEL].TFLG = PIT_TFLG_TIF_MASK;
}

void Motor_StartTimer(void) {
    NVIC_SetPriority(PIT_IRQn, 0u);
    PIT->CHANNEL[MOTOR_PIT_CHANNEL].TCTRL = PIT_TCTRL_TIE_MASK | PIT_TCTRL_TEN_MASK;
    NVIC_EnableIRQ(PIT_IRQn);
}

static void Motor_TimerISR(void) {
    uint32_t motor;

    if (ticksLeft == 0u) {
        load_stream_frame();
    }

    for (motor = 0; motor < NUM_MOTORS; motor++) {
        uint32_t oldPhase;

        // Step pulses only set high for one timer tick
        if (stepHigh[motor]) {
            step_set((uint8_t)motor, 0u);
            stepHigh[motor] = 0u;
        }

        if (speed[motor] == 0u) {
            continue;
        }

        // phase overflow means step
        oldPhase = phase[motor];
        phase[motor] += speed[motor];
        if (phase[motor] < oldPhase) {
            step_set((uint8_t)motor, 1u);
            stepHigh[motor] = 1u;
        }
    }

    if (ticksLeft > 0u) {
        ticksLeft--;
    }
}

void PIT_IRQHandler(void) {
    if (PIT->CHANNEL[MOTOR_PIT_CHANNEL].TFLG & PIT_TFLG_TIF_MASK) {
        PIT->CHANNEL[MOTOR_PIT_CHANNEL].TFLG = PIT_TFLG_TIF_MASK;
        Motor_TimerISR();
    }
}

uint8_t Motor_StreamPush(const MotorStreamFrame *frame) {
    uint32_t motor;
    uint8_t nextWrite;

    if (frame == 0 || framesQueued >= MOTOR_STREAM_BUFFER_FRAMES) {
        return 0u;
    }

    // Copy frame into queue and update write index
    nextWrite = writePos;
    frameQueue[nextWrite].duration = frame->duration;
    for (motor = 0; motor < NUM_MOTORS; motor++) {
        frameQueue[nextWrite].speed[motor] = frame->speed[motor];
    }

    nextWrite++;
    if (nextWrite >= MOTOR_STREAM_BUFFER_FRAMES) {
        nextWrite = 0u;
    }

    __disable_irq();
    writePos = nextWrite;
    framesQueued++;
    __enable_irq();
    return 1u;
}
