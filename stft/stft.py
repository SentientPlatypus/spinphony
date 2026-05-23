import math
from collections import deque

import numpy as np


SAMPLE_RATE = 8400

NUM_MOTORS = 4
NUM_NOTES = NUM_MOTORS

WINDOW_SIZE = 2048
HOP_SIZE = 256

MIN_MIDI_NOTE = 36
MAX_MIDI_NOTE = 96

SILENCE_RMS = 0.006
MIN_SCORE_RATIO = 0.20
MIN_BASE_NOTE_RATIO = 0.08
TRACK_MATCH_CENTS = 650.0

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def midi_to_freq(midi_note):
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))


def midi_to_name(midi_note):
    return f"{NOTE_NAMES[midi_note % 12]}{midi_note // 12 - 1}"


def cents_between(a, b):
    if a <= 0 or b <= 0:
        return float("inf")
    return abs(1200.0 * math.log2(a / b))


def is_harmonic_of(candidate_freq, selected_freq, tolerance_cents=45.0):
    if candidate_freq <= selected_freq:
        return False

    ratio = candidate_freq / selected_freq
    nearest = round(ratio)
    if nearest < 2 or nearest > 8:
        return False

    cents = abs(1200.0 * math.log2(ratio / nearest))
    return cents <= tolerance_cents


def note_label(freq):
    if freq <= 0:
        return "--"

    midi_note = round(69 + 12 * math.log2(freq / 440.0))
    return f"{midi_to_name(midi_note)} {freq:.2f} Hz"


def format_freqs(freqs):
    return " | ".join(note_label(float(freq)) for freq in freqs)


def build_dft(note_freqs, sample_rate):
    harmonic_weights = {
        1: 1.25,
        2: 0.38,
        3: 0.22,
        4: 0.14,
        5: 0.09,
        6: 0.06,
    }

    target_freqs = []
    target_note_indices = []
    target_harmonics = []
    target_weights = []
    nyquist = sample_rate / 2.0

    for note_idx, freq in enumerate(note_freqs):
        for harmonic, weight in harmonic_weights.items():
            harmonic_freq = float(freq) * harmonic
            if harmonic_freq >= nyquist:
                continue

            target_freqs.append(harmonic_freq)
            target_note_indices.append(note_idx)
            target_harmonics.append(harmonic)
            target_weights.append(weight)

    target_freqs = np.array(target_freqs, dtype=np.float32)
    sample_positions = np.arange(WINDOW_SIZE, dtype=np.float32)
    angles = (
        2.0
        * math.pi
        * target_freqs[:, None]
        * sample_positions[None, :]
        / sample_rate
    )

    return {
        "cos": np.cos(angles).astype(np.float32),
        "sin": np.sin(angles).astype(np.float32),
        "note_indices": np.array(target_note_indices, dtype=np.int32),
        "harmonics": np.array(target_harmonics, dtype=np.int32),
        "weights": np.array(target_weights, dtype=np.float32),
        "num_notes": len(note_freqs),
    }


def score_notes(windowed_frame, dft):
    real = dft["cos"] @ windowed_frame
    imag = -(dft["sin"] @ windowed_frame)
    magnitudes = np.sqrt(real * real + imag * imag).astype(np.float32)

    note_scores = np.zeros(dft["num_notes"], dtype=np.float32)
    base_note_scores = np.zeros(dft["num_notes"], dtype=np.float32)

    note_indices = dft["note_indices"]
    weighted_magnitudes = dft["weights"] * magnitudes
    np.add.at(note_scores, note_indices, weighted_magnitudes)
    np.maximum.at(
        base_note_scores,
        note_indices[dft["harmonics"] == 1],
        magnitudes[dft["harmonics"] == 1],
    )

    return note_scores, base_note_scores


def pick_best_notes(note_scores, base_note_scores, note_freqs, max_notes):
    max_score = float(np.max(note_scores))
    max_base_score = float(np.max(base_note_scores))

    if max_score <= 0.0 or max_base_score <= 0.0:
        return []

    score_floor = max_score * MIN_SCORE_RATIO
    base_score_floor = max_base_score * MIN_BASE_NOTE_RATIO

    selected = []
    local_peak = np.ones(len(note_scores), dtype=bool)
    local_peak[1:-1] = (note_scores[1:-1] >= note_scores[:-2]) & (
        note_scores[1:-1] >= note_scores[2:]
    )
    order = np.argsort(note_scores)[::-1]

    for note_index in order:
        score = float(note_scores[note_index])
        base_score = float(base_note_scores[note_index])
        freq = float(note_freqs[note_index])

        if not local_peak[note_index]:
            continue

        if score < score_floor or base_score < base_score_floor:
            continue

        too_close = any(cents_between(freq, item["freq"]) < 90.0 for item in selected)
        if too_close:
            continue

        harmonic_duplicate = False
        for item in selected:
            weak_extra_harmonic = base_score < item["base_score"] * 0.45
            if (
                is_harmonic_of(freq, item["freq"])
                and score < item["score"] * 0.90
                and weak_extra_harmonic
            ):
                harmonic_duplicate = True
                break

        if harmonic_duplicate:
            continue

        selected.append({"freq": freq, "score": score, "base_score": base_score})
        if len(selected) == max_notes:
            break

    return selected


def notes_to_freqs(notes):
    selected_notes = list(notes)
    selected_notes.sort(key=lambda item: item["freq"])

    if not selected_notes:
        return []

    return [item["freq"] for item in selected_notes]


def keep_motor_tracks(detected_freqs, last_motor_freqs):
    motor_freqs = np.zeros(NUM_NOTES, dtype=np.float32)

    remaining_detections = set(range(len(detected_freqs)))
    remaining_tracks = set(range(NUM_NOTES))
    pairs = []

    for motor_idx, last_freq in enumerate(last_motor_freqs):
        if last_freq <= 0:
            continue

        for detection_idx, detected_freq in enumerate(detected_freqs):
            distance = cents_between(float(last_freq), float(detected_freq))
            pairs.append((distance, motor_idx, detection_idx))

    for distance, motor_idx, detection_idx in sorted(pairs):
        if distance > TRACK_MATCH_CENTS:
            continue
        if motor_idx not in remaining_tracks or detection_idx not in remaining_detections:
            continue

        motor_freqs[motor_idx] = detected_freqs[detection_idx]
        remaining_tracks.remove(motor_idx)
        remaining_detections.remove(detection_idx)

    empty_tracks = [idx for idx in sorted(remaining_tracks) if last_motor_freqs[idx] <= 0]
    other_tracks = [idx for idx in sorted(remaining_tracks) if last_motor_freqs[idx] > 0]
    track_order = empty_tracks + other_tracks

    for track_idx, detection_idx in zip(track_order, sorted(remaining_detections)):
        motor_freqs[track_idx] = detected_freqs[detection_idx]

    return motor_freqs


class NoteAnalyzer:
    def __init__(self):
        midi_notes = [
            note
            for note in range(MIN_MIDI_NOTE, MAX_MIDI_NOTE + 1)
            if midi_to_freq(note) < SAMPLE_RATE / 2.0
        ]

        self.note_freqs = np.array([midi_to_freq(note) for note in midi_notes], dtype=np.float32)
        self.window = np.hanning(WINDOW_SIZE).astype(np.float32)
        self.dft = build_dft(self.note_freqs, SAMPLE_RATE)

        self.sample_buffer = np.zeros(WINDOW_SIZE * 8, dtype=np.float32)
        self.write_idx = 0
        self.samples_seen = 0
        self.samples_since_last_frame = 0
        self.first_frame_done = False
        self.last_motor_freqs = np.zeros(NUM_NOTES, dtype=np.float32)
        self.latest_audio_spectrum = np.zeros(len(self.note_freqs), dtype=np.float32)

    def push_samples(self, samples):
        output_frames = []

        for sample in samples:
            self.sample_buffer[self.write_idx] = sample
            self.write_idx = (self.write_idx + 1) % len(self.sample_buffer)
            self.samples_seen += 1

            if self.samples_seen < WINDOW_SIZE:
                continue

            if not self.first_frame_done:
                freqs = self._analyze_latest_window()
                output_frames.append(freqs)
                self.first_frame_done = True
                self.samples_since_last_frame = 0
                continue

            self.samples_since_last_frame += 1

            if self.samples_since_last_frame >= HOP_SIZE:
                freqs = self._analyze_latest_window()
                output_frames.append(freqs)
                self.samples_since_last_frame -= HOP_SIZE

        return output_frames

    def _latest_window(self):
        start = (self.write_idx - WINDOW_SIZE) % len(self.sample_buffer)

        if start < self.write_idx:
            return self.sample_buffer[start:self.write_idx].copy()

        return np.concatenate((self.sample_buffer[start:], self.sample_buffer[:self.write_idx]))

    def _analyze_latest_window(self):
        frame = self._latest_window()
        rms = float(np.sqrt(np.mean(frame * frame)))
        if rms < SILENCE_RMS:
            detected_freqs = []
            self.latest_audio_spectrum = np.zeros(len(self.note_freqs), dtype=np.float32)
        else:
            note_scores, base_note_scores = score_notes(frame * self.window, self.dft)
            selected = pick_best_notes(
                note_scores,
                base_note_scores,
                self.note_freqs,
                NUM_NOTES,
            )
            detected_freqs = notes_to_freqs(selected)

            peak = float(np.max(note_scores))
            if peak > 0.0:
                self.latest_audio_spectrum = np.sqrt(note_scores / peak).astype(np.float32)
            else:
                self.latest_audio_spectrum = np.zeros(len(self.note_freqs), dtype=np.float32)

        freqs = keep_motor_tracks(detected_freqs, self.last_motor_freqs)
        self.last_motor_freqs = freqs
        return freqs


class ShortNoteFilter:
    """Delays output by one frame to remove very short notes."""

    def __init__(self, min_frames):
        self.min_frames = max(1, int(min_frames))
        self.delay = self.min_frames - 1
        self.future_queue = deque()
        self.previous_raw = deque(maxlen=self.delay)

    def push_and_get_output(self, found_freqs):
        found_freqs = np.asarray(found_freqs, dtype=np.float32).copy()

        if self.delay == 0:
            return found_freqs

        self.future_queue.append(found_freqs)

        if len(self.future_queue) <= self.delay:
            return None

        oldest = self.future_queue.popleft()
        output = np.zeros(NUM_MOTORS, dtype=np.float32)

        future = list(self.future_queue)

        for track_idx in range(NUM_MOTORS):
            value = float(oldest[track_idx])

            if value <= 0.0:
                output[track_idx] = 0.0
                continue

            run_length = 1

            for previous_frame in reversed(self.previous_raw):
                if float(previous_frame[track_idx]) == value:
                    run_length += 1
                else:
                    break

            for future_frame in future:
                if float(future_frame[track_idx]) == value:
                    run_length += 1
                else:
                    break

            if run_length >= self.min_frames:
                output[track_idx] = value

        self.previous_raw.append(oldest)

        return output

    def flush(self):
        outputs = []

        for _ in range(self.delay):
            output = self.push_and_get_output(np.zeros(NUM_MOTORS, dtype=np.float32))
            if output is not None:
                outputs.append(output)

        return outputs
