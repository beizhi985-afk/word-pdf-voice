from __future__ import annotations

import os
import platform
import re
import subprocess
import tempfile
import threading
import time
from functools import lru_cache
from pathlib import Path

from .playback import play_wav_sync


class ChineseSpeechError(RuntimeError):
    pass


def meaning_for_speech(meaning: str, limit: int = 240) -> str:
    """Keep the Chinese parts of a dictionary meaning pleasant to listen to."""
    normalized = meaning.replace("...", "").replace("…", "")
    chunks = re.findall(r"[\u3400-\u9fff，。；、？！：（）《》]+", normalized)
    text = "，".join(chunk.strip("，。；、") for chunk in chunks if chunk.strip("，。；、"))
    return text[:limit].rstrip("，；、")


def _powershell_command() -> list[str]:
    script = r"""
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Speech
$outputPath = [Environment]::GetEnvironmentVariable('WORD_VOICE_CHINESE_WAV')
if ([string]::IsNullOrWhiteSpace($outputPath)) {
    [Console]::Error.Write('没有收到中文语音输出路径')
    exit 4
}
$text = [Console]::In.ReadToEnd()
$speaker = [System.Speech.Synthesis.SpeechSynthesizer]::new()
$voice = $speaker.GetInstalledVoices() |
    Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'zh-*' } |
    Select-Object -First 1
if ($null -eq $voice) {
    [Console]::Error.Write('没有安装 Windows 中文语音')
    exit 3
}
$speaker.SelectVoice($voice.VoiceInfo.Name)
$speaker.Rate = -1
$speaker.SetOutputToWaveFile($outputPath)
try {
    $speaker.Speak($text)
} finally {
    $speaker.SetOutputToNull()
    $speaker.Dispose()
}
""".strip()
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script]


@lru_cache(maxsize=1)
def chinese_voice_available() -> bool:
    if platform.system() != "Windows":
        return False
    probe = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$speaker = [System.Speech.Synthesis.SpeechSynthesizer]::new()
$voice = $speaker.GetInstalledVoices() |
    Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'zh-*' } |
    Select-Object -First 1
if ($null -eq $voice) { exit 3 }
""".strip()
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", probe],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=10,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def speak_chinese(meaning: str, stop_event: threading.Event | None = None) -> bool:
    text = meaning_for_speech(meaning)
    if not text:
        return True
    if platform.system() != "Windows":
        raise ChineseSpeechError("中文释义朗读目前仅支持 Windows")
    temporary = tempfile.NamedTemporaryFile(prefix="word-voice-zh-", suffix=".wav", delete=False)
    output_path = Path(temporary.name)
    temporary.close()
    try:
        process = subprocess.Popen(
            _powershell_command(),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env={**os.environ, "WORD_VOICE_CHINESE_WAV": str(output_path)},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        assert process.stdin is not None
        process.stdin.write(text.encode("utf-8"))
        process.stdin.close()
        while process.poll() is None:
            if stop_event and stop_event.is_set():
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                return False
            time.sleep(0.05)
        error = (
            process.stderr.read().decode("utf-8", errors="replace")
            if process.stderr
            else ""
        )
        if process.returncode != 0:
            raise ChineseSpeechError(error.strip() or "Windows 中文语音生成失败")
        return play_wav_sync(output_path, stop_event)
    finally:
        output_path.unlink(missing_ok=True)
