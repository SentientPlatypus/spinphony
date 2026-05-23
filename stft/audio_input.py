import numpy as np
import soundcard as sc

VIRTUAL_DEVICE_KEYWORDS = (
    "cable output",
    "vb-audio",
    "voicemeeter",
    "virtual cable",
    "blackhole",
)

LIVE_NORMALIZER_PEAK_FLOOR = 0.05
LIVE_NORMALIZER_DECAY = 0.9995


def mono_float32(audio):
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    return audio.astype(np.float32, copy=False)


def choose_system_audio_device():
    microphones = sc.all_microphones(include_loopback=True)

    for mic in microphones:
        name = mic.name.lower()
        if any(keyword in name for keyword in VIRTUAL_DEVICE_KEYWORDS):
            return mic

    names = "\n".join(mic.name for mic in microphones)
    raise RuntimeError(
        "Could not find a virtual cable input.\n\n"
        "Install VB-CABLE or Voicemeeter, then set the app/browser/player output "
        "to CABLE Input. This script records from CABLE Output.\n\n"
        "Available recording devices:\n"
        + names
    )


class SimpleResampler:
    """Converts capture-rate audio blocks into analysis-rate samples."""

    def __init__(self, source_rate, target_rate):
        self.source_rate = float(source_rate)
        self.target_rate = float(target_rate)
        self.source_per_target = self.source_rate / self.target_rate
        self.source_base_index = 0
        self.next_target_index = 0

    def process(self, source_block):
        source_block = np.asarray(source_block, dtype=np.float32)
        block_len = len(source_block)
        block_start = self.source_base_index
        block_end = block_start + block_len

        output = []

        while True:
            source_index = int(round(self.next_target_index * self.source_per_target))
            if source_index >= block_end:
                break

            if source_index >= block_start:
                output.append(source_block[source_index - block_start])

            self.next_target_index += 1

        self.source_base_index = block_end

        if not output:
            return np.zeros(0, dtype=np.float32)

        return np.asarray(output, dtype=np.float32)


class VolumeNormalizer:
    """Rolling peak normalization for live audio blocks."""

    def __init__(self, floor=LIVE_NORMALIZER_PEAK_FLOOR, decay=LIVE_NORMALIZER_DECAY):
        self.floor = float(floor)
        self.decay = float(decay)
        self.peak = float(floor)

    def process(self, samples):
        samples = np.asarray(samples, dtype=np.float32)
        if len(samples) == 0:
            return samples

        block_peak = float(np.max(np.abs(samples)))
        self.peak = max(self.floor, block_peak, self.peak * self.decay)

        return (samples / self.peak).astype(np.float32, copy=False)
