from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

from word_voice.playback import AudioPlaybackError, _read_pcm_wave


class PlaybackTests(unittest.TestCase):
    def test_pcm_wave_is_loaded_with_exact_device_format(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.wav"
            with wave.open(str(path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(24000)
                output.writeframes(b"\x00\x00" * 24)

            audio_format, frames = _read_pcm_wave(path)

            self.assertEqual(1, audio_format.wFormatTag)
            self.assertEqual(1, audio_format.nChannels)
            self.assertEqual(24000, audio_format.nSamplesPerSec)
            self.assertEqual(16, audio_format.wBitsPerSample)
            self.assertEqual(48, len(frames))

    def test_missing_wave_has_clear_error(self) -> None:
        with self.assertRaisesRegex(AudioPlaybackError, "找不到音频文件"):
            _read_pcm_wave(Path("missing.wav"))


if __name__ == "__main__":
    unittest.main()
