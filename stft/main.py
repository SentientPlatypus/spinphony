import threading

import numpy as np

from audio_input import SimpleResampler, VolumeNormalizer, choose_system_audio_device, mono_float32
from live_ui import UiState, run_live_visualizer
from motor_serial import MotorClock, MotorSerial
from stft import (
    NoteAnalyzer,
    ShortNoteFilter,
    SAMPLE_RATE,
)

CAPTURE_START_RMS = 0.0008
CAPTURE_SAMPLE_RATE = 48000
CAPTURE_BLOCK_SIZE = 1024

DEFAULT_SERIAL_PORT = "COM5"
SERIAL_BAUD_RATE = 230400
DEFAULT_UI_WINDOW_SECONDS = 12.0

MIN_NOTE_FRAMES = 1


def stream_live():
    ui_state = UiState(DEFAULT_UI_WINDOW_SECONDS)
    stop_event = threading.Event()

    def worker():
        try:
            stream_live_loop(ui_state=ui_state, stop_event=stop_event)
            ui_state.publish_status("Stream ended")
        except Exception as exc:
            ui_state.publish_status(f"Stream error: {exc}")

    thread = threading.Thread(target=worker, name="stft-stream", daemon=True)
    thread.start()

    try:
        run_live_visualizer(ui_state, stop_event)
    finally:
        stop_event.set()
        thread.join(timeout=2.0)


def stream_live_loop(ui_state=None, stop_event=None):
    input_device = choose_system_audio_device()

    resampler = SimpleResampler(CAPTURE_SAMPLE_RATE, SAMPLE_RATE)
    volume = VolumeNormalizer()
    notes = NoteAnalyzer()
    short_note_filter = ShortNoteFilter(MIN_NOTE_FRAMES)
    motor_clock = MotorClock()
    motor_serial = MotorSerial(DEFAULT_SERIAL_PORT, SERIAL_BAUD_RATE)

    audio_status = "Waiting for audio"
    serial_connected = False
    if ui_state is not None:
        publish_status(ui_state, audio_status, serial_connected)

    started = False
    frames_sent = 0

    with input_device.recorder(
        samplerate=CAPTURE_SAMPLE_RATE,
        channels=[0, 1],
        blocksize=CAPTURE_BLOCK_SIZE,
    ) as recorder:
        try:
            while True:
                if stop_event is not None and stop_event.is_set():
                    break

                source_block = recorder.record(numframes=CAPTURE_BLOCK_SIZE)
                source_block = mono_float32(source_block)
                rms = float(np.sqrt(np.mean(source_block * source_block))) if len(source_block) else 0.0

                if not started:
                    if rms < CAPTURE_START_RMS:
                        continue

                    started = True
                    audio_status = "Audio started"
                    if ui_state is not None:
                        publish_status(ui_state, audio_status, serial_connected)

                process_block = volume.process(source_block)
                target_samples = resampler.process(process_block)
                found_frames = notes.push_samples(target_samples)

                for found_freqs in found_frames:
                    motor_freqs = short_note_filter.push_and_get_output(found_freqs)
                    if motor_freqs is None:
                        continue

                    ticks, new_serial_connected = motor_serial.send_frame(motor_clock, motor_freqs)
                    frames_sent += 1
                    if new_serial_connected != serial_connected:
                        serial_connected = new_serial_connected
                        if ui_state is not None:
                            publish_status(ui_state, audio_status, serial_connected)

                    if ui_state is not None:
                        ui_state.publish_frame(notes.latest_audio_spectrum, motor_freqs, frames_sent, ticks)

        except KeyboardInterrupt:
            pass

        finally:
            for motor_freqs in short_note_filter.flush():
                motor_serial.send_frame(motor_clock, motor_freqs)

            motor_serial.send_silence_tail(motor_clock)
            motor_serial.close()


def publish_status(ui_state, audio_status, serial_connected):
    serial_status = "serial connected" if serial_connected else "serial offline"
    ui_state.publish_status(f"{audio_status} | {serial_status}")


def main():
    stream_live()


if __name__ == "__main__":
    main()
