#include "serial_stream.h"

#include <stdint.h>

#include "MKL46Z4.h"
#include "constants.h"
#include "motor.h"

#define STREAM_SYNC 0xA5u
#define STREAM_PACKET_SIZE 20u
#define SERIAL_UART_OVERSAMPLE 13u
#define SERIAL_UART_SBR ((RUN_HZ + ((SERIAL_BAUD_RATE * SERIAL_UART_OVERSAMPLE) / 2u)) / \
                         (SERIAL_BAUD_RATE * SERIAL_UART_OVERSAMPLE))
#define UART_RX_DMA_CHANNEL 0u
#define UART0_RX_DMAMUX_SOURCE 2u
#define UART_RX_DMA_CHUNK_SIZE STREAM_PACKET_SIZE

#define DMA_STATUS_CLEAR_MASK (DMA_DSR_BCR_DONE_MASK | \
                               DMA_DSR_BCR_BES_MASK |  \
                               DMA_DSR_BCR_BED_MASK |  \
                               DMA_DSR_BCR_CE_MASK)

// Buffer that DMA fills while CPU is working on other stuff
static volatile uint8_t dmaBuffer[UART_RX_DMA_CHUNK_SIZE];
static uint8_t parseBuffer[UART_RX_DMA_CHUNK_SIZE];

/* 20-byte packets that come in from serial */
static uint8_t packet[STREAM_PACKET_SIZE];
static uint8_t packetPos = 0u;

static void uart_dma_start(void);
static void parse_byte(uint8_t value);

static void uart_dma_stop_requests(void) {
    // Pause DMA before changing DMA register
    UART0->C5 &= (uint8_t)~UART0_C5_RDMAE_MASK;
    DMAMUX0->CHCFG[UART_RX_DMA_CHANNEL] = 0u;
    DMA0->DMA[UART_RX_DMA_CHANNEL].DCR = 0u;
}

static void uart_dma_start(void) {
    uart_dma_stop_requests();

    // Transfer one packet from UART to DMA buffer
    DMA0->DMA[UART_RX_DMA_CHANNEL].DSR_BCR = DMA_STATUS_CLEAR_MASK;
    DMA0->DMA[UART_RX_DMA_CHANNEL].SAR = (uint32_t)(uintptr_t)&UART0->D;
    DMA0->DMA[UART_RX_DMA_CHANNEL].DAR = (uint32_t)(uintptr_t)&dmaBuffer[0u];
    DMA0->DMA[UART_RX_DMA_CHANNEL].DSR_BCR = DMA_DSR_BCR_BCR(UART_RX_DMA_CHUNK_SIZE);
    DMA0->DMA[UART_RX_DMA_CHANNEL].DCR = DMA_DCR_D_REQ_MASK |
                                         DMA_DCR_DINC_MASK |
                                         DMA_DCR_SSIZE(1u) |
                                         DMA_DCR_DSIZE(1u) |
                                         DMA_DCR_CS_MASK |
                                         DMA_DCR_ERQ_MASK;

    DMAMUX0->CHCFG[UART_RX_DMA_CHANNEL] =
        DMAMUX_CHCFG_SOURCE(UART0_RX_DMAMUX_SOURCE) | DMAMUX_CHCFG_ENBL_MASK;
    UART0->C5 |= UART0_C5_RDMAE_MASK;
}

static uint32_t read_u32_le(const uint8_t *data) {
    // serial bytes into motor increment
    return ((uint32_t)data[0]) |
           ((uint32_t)data[1] << 8) |
           ((uint32_t)data[2] << 16) |
           ((uint32_t)data[3] << 24);
}

static void handle_packet(void) {
    uint8_t motor;
    uint8_t checksum = 0u;

    // XOR checksum that catches issues
    for (motor = 0u; motor < (STREAM_PACKET_SIZE - 1u); motor++) {
        checksum ^= packet[motor];
    }
    if (checksum == packet[STREAM_PACKET_SIZE - 1u]) {
        MotorStreamFrame frame;
        frame.duration = (uint16_t)(((uint16_t)packet[1]) | ((uint16_t)packet[2] << 8));
        for (motor = 0u; motor < NUM_MOTORS; motor++) {
            frame.speed[motor] = read_u32_le(&packet[3u + ((uint32_t)motor * 4u)]);
        }

        // If the motor queue is full this frame is dropped
        (void)Motor_StreamPush(&frame);
    }
}

static void parse_byte(uint8_t value) {
    // Ignore bytes until we see 0xA5
    if (packetPos == 0u) {
        if (value == STREAM_SYNC) {
            packet[packetPos] = value;
            packetPos = 1u;
        }
        return;
    }

    packet[packetPos] = value;
    packetPos++;
    if (packetPos >= STREAM_PACKET_SIZE) {
        handle_packet();
        packetPos = 0u;
    }
}

void SerialStream_Init(void) {
    // UART0 and DMA clocks
    SIM->SCGC4 |= SIM_SCGC4_UART0_MASK;
    SIM->SCGC6 |= SIM_SCGC6_DMAMUX_MASK;
    SIM->SCGC7 |= SIM_SCGC7_DMA_MASK;
    SIM->SOPT2 = (SIM->SOPT2 & ~SIM_SOPT2_UART0SRC_MASK) | SIM_SOPT2_UART0SRC(1u);

    packetPos = 0u;

    // UART setup using baud rate
    UART0->C2 = 0u;
    UART0->C5 = 0u;
    UART0->BDH = (UART0->BDH & ~(UART_BDH_SBR_MASK | UART_BDH_SBNS_MASK)) |
                 UART_BDH_SBR(SERIAL_UART_SBR >> 8);
    UART0->BDL = UART_BDL_SBR(SERIAL_UART_SBR);
    UART0->C4 = (UART0->C4 & ~UART0_C4_OSR_MASK) | UART0_C4_OSR(SERIAL_UART_OVERSAMPLE - 1u);
    UART0->C1 = 0u;
    UART0->C3 = 0u;
    UART0->C2 = UART_C2_RE_MASK | UART_C2_TE_MASK;

    // flushing old bytes before starting DMA
    while (UART0->S1 & UART_S1_RDRF_MASK) {
        (void)UART0->D;
    }

    NVIC_DisableIRQ(UART0_IRQn);
    NVIC_DisableIRQ(DMA0_IRQn);
    uart_dma_start();
}

void SerialStream_Service(void) {
    uint32_t status = DMA0->DMA[UART_RX_DMA_CHANNEL].DSR_BCR;
    uint8_t i;

    // Error, restart DMA
    if ((status & (DMA_DSR_BCR_BES_MASK | DMA_DSR_BCR_BED_MASK | DMA_DSR_BCR_CE_MASK)) != 0u) {
        uart_dma_start();
        return;
    }

    // DMA is done collecting packets
    if ((status & DMA_DSR_BCR_DONE_MASK) == 0u) {
        return;
    }

    for (i = 0u; i < UART_RX_DMA_CHUNK_SIZE; i++) {
        parseBuffer[i] = dmaBuffer[i];
    }

    // restart DMA
    uart_dma_start();

    for (i = 0u; i < UART_RX_DMA_CHUNK_SIZE; i++) {
        parse_byte(parseBuffer[i]);
    }
}

void UART0_IRQHandler(void) {
    // UART interrupts off
    UART0->C2 &= (uint8_t)~(UART_C2_RIE_MASK | UART_C2_ILIE_MASK);
}

void DMA0_IRQHandler(void) {
    uint32_t status = DMA0->DMA[UART_RX_DMA_CHANNEL].DSR_BCR;

    // clear DMA status bits, disable IRQ
    DMA0->DMA[UART_RX_DMA_CHANNEL].DSR_BCR = status & DMA_STATUS_CLEAR_MASK;
    NVIC_DisableIRQ(DMA0_IRQn);
}
