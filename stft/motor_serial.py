import struct
import time

import numpy as np
import serial

from stft import (
    HOP_SIZE,
    NUM_MOTORS,
    SAMPLE_RATE,
)

MOTOR_CONTROL_RATE = 20000
PHASE_SCALE = 1 << 32

STREAM_SYNC = 0xA5
STREAM_PACKET_SIZE = 20


def freq_tracks_to_phase_increments(freq_tracks):
    increments = np.rint(freq_tracks * PHASE_SCALE / MOTOR_CONTROL_RATE)
    return increments.astype(np.uint32)


def make_stream_packet(duration_ticks, freqs):
    duration_ticks = max(1, min(0xFFFF, int(round(duration_ticks))))

    freqs = np.asarray(freqs, dtype=np.float32)
    if freqs.shape[0] != NUM_MOTORS:
        raise ValueError(f"Expected {NUM_MOTORS} motor frequencies, got {freqs.shape[0]}")

    phase_increments = freq_tracks_to_phase_increments(freqs.reshape(1, NUM_MOTORS))[0]

    packet = bytearray()
    packet.append(STREAM_SYNC)
    packet += struct.pack("<H", duration_ticks)

    for inc in phase_increments:
        packet += struct.pack("<I", int(inc))

    checksum = 0
    for value in packet:
        checksum ^= value

    packet.append(checksum)

    if len(packet) != STREAM_PACKET_SIZE:
        raise RuntimeError(f"Bad packet size: {len(packet)}")

    return bytes(packet)


class MotorClock:
    """Motor tick durations with bounded rounding drift."""

    def __init__(self):
        self.frame_index = 0

    def next_ticks(self):
        previous_total = round(
            self.frame_index * HOP_SIZE * MOTOR_CONTROL_RATE / float(SAMPLE_RATE)
        )
        self.frame_index += 1
        next_total = round(
            self.frame_index * HOP_SIZE * MOTOR_CONTROL_RATE / float(SAMPLE_RATE)
        )

        return max(1, min(0xFFFF, next_total - previous_total))


def write_packet(serial_port, packet, max_retry_seconds=2.0):
    total_written = 0
    start = time.perf_counter()

    while total_written < len(packet):
        written = serial_port.write(packet[total_written:])

        if written is None:
            written = len(packet) - total_written

        if written == 0:
            if time.perf_counter() - start > max_retry_seconds:
                raise RuntimeError(
                    f"Serial write stalled: wrote {total_written} of {len(packet)} bytes"
                )
            continue

        total_written += written


class MotorSerial:
    def __init__(self, port, baud, retry_seconds=1.0):
        self.port = port
        self.baud = baud
        self.retry_seconds = float(retry_seconds)
        self.connection = None
        self.next_retry_at = 0.0

    def close(self):
        if self.connection is None:
            return

        try:
            self.connection.close()
        finally:
            self.connection = None

    def send_frame(self, motor_clock, freqs):
        ticks = motor_clock.next_ticks()

        if self.connection is None and not self._connect_if_due():
            return ticks, False

        try:
            packet = make_stream_packet(ticks, freqs)
            write_packet(self.connection, packet)
            return ticks, True
        except (OSError, RuntimeError, serial.SerialException):
            self.close()
            self.next_retry_at = time.perf_counter() + self.retry_seconds
            return ticks, False

    def send_silence_tail(self, motor_clock, count=16):
        if self.connection is None:
            return

        silence_freqs = np.zeros(NUM_MOTORS, dtype=np.float32)

        for _ in range(count):
            if not self.send_frame(motor_clock, silence_freqs)[1]:
                return

        self.connection.flush()

    def _connect_if_due(self):
        now = time.perf_counter()
        if now < self.next_retry_at:
            return False

        try:
            self.connection = serial.Serial(self.port, baudrate=self.baud, timeout=0, write_timeout=1)
            return True
        except (OSError, serial.SerialException):
            self.connection = None
            self.next_retry_at = now + self.retry_seconds
            return False
