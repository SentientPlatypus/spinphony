import math
import threading
from collections import deque

import numpy as np

from stft import (
    format_freqs,
    HOP_SIZE,
    MAX_MIDI_NOTE,
    midi_to_freq,
    MIN_MIDI_NOTE,
    NUM_MOTORS,
    SAMPLE_RATE,
)


class UiState:
    def __init__(self, window_seconds):
        self.window_seconds = max(1.0, float(window_seconds))
        self.frame_duration = HOP_SIZE / float(SAMPLE_RATE)
        self.max_history = int(math.ceil(self.window_seconds / self.frame_duration)) + 8
        self.lock = threading.Lock()
        self.spectrum_frames = deque(maxlen=self.max_history)
        self.motor_frames = deque(maxlen=self.max_history)
        self.current_spectrum = np.zeros(MAX_MIDI_NOTE - MIN_MIDI_NOTE + 1, dtype=np.float32)
        self.current_motor = np.zeros(NUM_MOTORS, dtype=np.float32)
        self.current_time = 0.0
        self.frames_sent = 0
        self.last_ticks = 0
        self.status = "Waiting for audio"

    def publish_status(self, status):
        with self.lock:
            self.status = status

    def publish_frame(self, spectrum, motor_freqs, frames_sent, ticks):
        timestamp = max(0.0, (int(frames_sent) - 1) * self.frame_duration)
        spectrum = np.asarray(spectrum, dtype=np.float32).copy()
        motor_freqs = np.asarray(motor_freqs, dtype=np.float32).copy()

        with self.lock:
            self.current_spectrum = spectrum
            self.current_motor = motor_freqs
            self.current_time = timestamp
            self.frames_sent = int(frames_sent)
            self.last_ticks = int(ticks)
            self.spectrum_frames.append((timestamp, spectrum))
            self.motor_frames.append((timestamp, motor_freqs))

    def snapshot(self):
        with self.lock:
            return {
                "spectrum_frames": list(self.spectrum_frames),
                "motor_frames": list(self.motor_frames),
                "current_motor": self.current_motor.copy(),
                "current_time": self.current_time,
                "frames_sent": self.frames_sent,
                "last_ticks": self.last_ticks,
                "status": self.status,
                "window_seconds": self.window_seconds,
                "frame_duration": self.frame_duration,
            }


class LiveWindow:
    COLORS = ("#55b7ff", "#ffd45f", "#63e38b", "#ff5f86")
    BG = "#090d14"
    PANEL_BG = "#121923"
    PANEL_EDGE = "#344155"
    GRID = "#253042"
    TEXT = "#e8eef8"
    MUTED = "#8d9aae"

    def __init__(self, root, state, stop_event):
        self.root = root
        self.state = state
        self.stop_event = stop_event

        self.root.title("Live STFT Motor Frequencies")
        self.root.configure(bg=self.BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.header = None
        self.canvas = None
        self._build_widgets()
        self._draw()

    def _build_widgets(self):
        import tkinter as tk

        self.header = tk.Label(
            self.root,
            anchor="w",
            bg=self.BG,
            fg=self.TEXT,
            font=("Segoe UI", 11),
            padx=10,
            pady=8,
        )
        self.header.pack(fill="x")

        self.canvas = tk.Canvas(
            self.root,
            width=1120,
            height=620,
            bg=self.BG,
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

    def close(self):
        self.stop_event.set()
        self.root.destroy()

    def _draw(self):
        snapshot = self.state.snapshot()
        self.header.configure(text=self._header_text(snapshot))

        width = max(640, self.canvas.winfo_width())
        height = max(420, self.canvas.winfo_height())
        panel_gap = 20
        margin_left = 72
        margin_right = 24
        margin_top = 24
        margin_bottom = 34
        panel_height = (height - margin_top - margin_bottom - panel_gap) / 2.0

        self.canvas.delete("all")
        self._draw_background(width, height)
        self._draw_spectrogram_panel(
            "Computer audio currently playing",
            snapshot["spectrum_frames"],
            snapshot["current_time"],
            snapshot["window_seconds"],
            margin_left,
            margin_top,
            width - margin_left - margin_right,
            panel_height,
            snapshot["frame_duration"],
        )
        self._draw_panel(
            "Fourier reconstruction with 4 frequencies",
            snapshot["motor_frames"],
            snapshot["current_time"],
            snapshot["window_seconds"],
            margin_left,
            margin_top + panel_height + panel_gap,
            width - margin_left - margin_right,
            panel_height,
            snapshot["frame_duration"],
        )

        if not self.stop_event.is_set():
            self.root.after(66, self._draw)

    def _header_text(self, snapshot):
        motor = format_freqs(snapshot["current_motor"])
        return (
            f"{snapshot['status']}   "
            f"frames={snapshot['frames_sent']} ticks={snapshot['last_ticks']}   "
            f"motor: {motor}"
        )

    def _draw_spectrogram_panel(self, title, frames, current_time, window_seconds, x, y, width, height, frame_duration):
        y_min = MIN_MIDI_NOTE
        y_max = MAX_MIDI_NOTE
        visible_start = max(0.0, current_time - window_seconds)
        visible_end = visible_start + window_seconds

        plot_x, plot_y, plot_width, plot_height = self._draw_panel_chrome(title, x, y, width, height, "spectrogram")
        self._draw_grid(plot_x, plot_y, plot_width, plot_height, y_min, y_max, visible_start, visible_end, window_seconds)

        note_height = max(2.0, plot_height / float(y_max - y_min + 1))
        for frame_time, spectrum in frames:
            frame_end = frame_time + frame_duration
            if frame_end < visible_start or frame_time > visible_end:
                continue

            x0 = plot_x + (frame_time - visible_start) / window_seconds * plot_width
            x1 = plot_x + (frame_end - visible_start) / window_seconds * plot_width
            x0 = max(plot_x, min(plot_x + plot_width, x0))
            x1 = max(x0 + 2, min(plot_x + plot_width, x1))

            for note_offset, strength in enumerate(spectrum):
                strength = float(strength)
                if strength < 0.035:
                    continue

                freq = midi_to_freq(MIN_MIDI_NOTE + note_offset)
                note_y = self._freq_to_y(freq, plot_y, plot_height, y_min, y_max)
                color = self._spectrogram_color(strength)
                self.canvas.create_rectangle(
                    x0,
                    note_y - note_height * 0.55,
                    x1,
                    note_y + note_height * 0.55,
                    fill=color,
                    outline=color,
                )

        self._draw_playhead(current_time, visible_start, window_seconds, plot_x, plot_y, plot_width, plot_height)

    def _draw_panel(self, title, frames, current_time, window_seconds, x, y, width, height, frame_duration):
        y_min = MIN_MIDI_NOTE
        y_max = MAX_MIDI_NOTE
        visible_start = max(0.0, current_time - window_seconds)
        visible_end = visible_start + window_seconds

        plot_x, plot_y, plot_width, plot_height = self._draw_panel_chrome(title, x, y, width, height, "fourier")
        self._draw_grid(plot_x, plot_y, plot_width, plot_height, y_min, y_max, visible_start, visible_end, window_seconds)

        for frame_time, freqs in frames:
            frame_end = frame_time + frame_duration
            if frame_end < visible_start or frame_time > visible_end:
                continue

            x0 = plot_x + (frame_time - visible_start) / window_seconds * plot_width
            x1 = plot_x + (frame_end - visible_start) / window_seconds * plot_width
            x0 = max(plot_x, min(plot_x + plot_width, x0))
            x1 = max(x0 + 2, min(plot_x + plot_width, x1))

            for track_idx, freq in enumerate(freqs):
                freq = float(freq)
                if freq <= 0.0:
                    continue

                note_y = self._freq_to_y(freq, plot_y, plot_height, y_min, y_max)
                color = self.COLORS[track_idx % len(self.COLORS)]
                self.canvas.create_rectangle(x0, note_y - 5, x1, note_y + 5, fill="#101723", outline="")
                self.canvas.create_rectangle(x0, note_y - 3, x1, note_y + 3, fill=color, outline=color)

        self._draw_playhead(current_time, visible_start, window_seconds, plot_x, plot_y, plot_width, plot_height)

    def _draw_background(self, width, height):
        steps = 28
        for idx in range(steps):
            t = idx / max(1, steps - 1)
            red = int(8 + 10 * t)
            green = int(12 + 12 * t)
            blue = int(21 + 21 * t)
            color = f"#{red:02x}{green:02x}{blue:02x}"
            y0 = height * idx / steps
            y1 = height * (idx + 1) / steps + 1
            self.canvas.create_rectangle(0, y0, width, y1, fill=color, outline="")

    def _draw_panel_chrome(self, title, x, y, width, height, mode):
        header_height = 34
        plot_padding = 10
        accent = "#5eead4" if mode == "spectrogram" else "#ffd166"

        self.canvas.create_rectangle(x + 5, y + 7, x + width + 5, y + height + 7, fill="#05070c", outline="")
        self.canvas.create_rectangle(x, y, x + width, y + height, fill=self.PANEL_BG, outline=self.PANEL_EDGE, width=1)
        self.canvas.create_rectangle(x, y, x + width, y + header_height, fill="#182233", outline="")
        self.canvas.create_line(x, y + header_height, x + width, y + header_height, fill="#33445d")
        self.canvas.create_rectangle(x, y, x + width, y + 3, fill=accent, outline=accent)
        self.canvas.create_text(
            x + 14,
            y + 8,
            text=title,
            fill=self.TEXT,
            anchor="nw",
            font=("Segoe UI", 12, "bold"),
        )
        plot_x = x + plot_padding
        plot_y = y + header_height + plot_padding
        plot_width = width - plot_padding * 2
        plot_height = height - header_height - plot_padding * 2
        self.canvas.create_rectangle(plot_x, plot_y, plot_x + plot_width, plot_y + plot_height, fill="#0d131d", outline="#223047")
        return plot_x, plot_y, plot_width, plot_height

    def _draw_playhead(self, current_time, visible_start, window_seconds, x, y, width, height):
        playhead_x = x + (current_time - visible_start) / window_seconds * width
        self.canvas.create_line(playhead_x - 1, y, playhead_x - 1, y + height, fill="#1d2a3d", width=3)
        self.canvas.create_line(playhead_x, y, playhead_x, y + height, fill="#f8fbff", width=2)
        self.canvas.create_oval(playhead_x - 4, y - 4, playhead_x + 4, y + 4, fill="#f8fbff", outline="")

    def _draw_grid(self, x, y, width, height, y_min, y_max, visible_start, visible_end, window_seconds):
        for midi_note in range(y_min, y_max + 1, 12):
            grid_y = self._freq_to_y(midi_to_freq(midi_note), y, height, y_min, y_max)
            self.canvas.create_line(x, grid_y, x + width, grid_y, fill=self.GRID)
            self.canvas.create_text(
                x - 8,
                grid_y,
                text=str(midi_note),
                fill=self.MUTED,
                anchor="e",
                font=("Segoe UI", 8),
            )

        tick_seconds = 2.0
        first_tick = math.ceil(visible_start / tick_seconds) * tick_seconds
        tick = first_tick
        while tick <= visible_end + 0.001:
            tick_x = x + (tick - visible_start) / window_seconds * width
            self.canvas.create_line(tick_x, y, tick_x, y + height, fill=self.GRID)
            self.canvas.create_text(
                tick_x,
                y + height + 14,
                text=f"{tick:.0f}s",
                fill=self.MUTED,
                anchor="n",
                font=("Segoe UI", 8),
            )
            tick += tick_seconds

    def _spectrogram_color(self, strength):
        strength = max(0.0, min(1.0, float(strength)))
        red = int(35 + 220 * strength)
        green = int(90 + 150 * math.sqrt(strength))
        blue = int(150 + 60 * (1.0 - strength))
        return f"#{red:02x}{green:02x}{blue:02x}"

    def _freq_to_y(self, freq, y, height, y_min, y_max):
        midi_note = 69.0 + 12.0 * math.log2(max(float(freq), 1.0) / 440.0)
        midi_note = max(y_min, min(y_max, midi_note))
        return y + (y_max - midi_note) / (y_max - y_min) * height


def run_live_visualizer(state, stop_event):
    import tkinter as tk

    root = tk.Tk()
    LiveWindow(root, state, stop_event)
    root.mainloop()
