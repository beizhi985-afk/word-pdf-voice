from __future__ import annotations

import ctypes
import sys
import threading
import time
import wave
from pathlib import Path


class AudioPlaybackError(RuntimeError):
    pass


class _WaveFormatEx(ctypes.Structure):
    _fields_ = (
        ("wFormatTag", ctypes.c_ushort),
        ("nChannels", ctypes.c_ushort),
        ("nSamplesPerSec", ctypes.c_uint32),
        ("nAvgBytesPerSec", ctypes.c_uint32),
        ("nBlockAlign", ctypes.c_ushort),
        ("wBitsPerSample", ctypes.c_ushort),
        ("cbSize", ctypes.c_ushort),
    )


class _WaveHeader(ctypes.Structure):
    _fields_ = (
        ("lpData", ctypes.c_void_p),
        ("dwBufferLength", ctypes.c_uint32),
        ("dwBytesRecorded", ctypes.c_uint32),
        ("dwUser", ctypes.c_size_t),
        ("dwFlags", ctypes.c_uint32),
        ("dwLoops", ctypes.c_uint32),
        ("lpNext", ctypes.c_void_p),
        ("reserved", ctypes.c_size_t),
    )


_WAVE_FORMAT_PCM = 1
_WAVE_MAPPER = 0xFFFFFFFF
_CALLBACK_NULL = 0
_WHDR_DONE = 0x00000001
_WAVERR_STILLPLAYING = 33


def _read_pcm_wave(path: str | Path) -> tuple[_WaveFormatEx, bytes]:
    source = Path(path)
    if not source.is_file():
        raise AudioPlaybackError(f"找不到音频文件：{source}")
    try:
        with wave.open(str(source), "rb") as audio:
            channels = audio.getnchannels()
            sample_width = audio.getsampwidth()
            sample_rate = audio.getframerate()
            compression = audio.getcomptype()
            frames = audio.readframes(audio.getnframes())
    except (OSError, EOFError, wave.Error) as exc:
        raise AudioPlaybackError(f"无法读取 WAV 音频：{source.name}（{exc}）") from exc
    if compression != "NONE" or sample_width not in (1, 2, 3, 4):
        raise AudioPlaybackError(f"暂不支持该 WAV 格式：{source.name}")
    block_align = channels * sample_width
    return (
        _WaveFormatEx(
            _WAVE_FORMAT_PCM,
            channels,
            sample_rate,
            sample_rate * block_align,
            block_align,
            sample_width * 8,
            0,
        ),
        frames,
    )


def _winmm_error(winmm, code: int) -> str:
    message = ctypes.create_unicode_buffer(256)
    if winmm.waveOutGetErrorTextW(code, message, len(message)) == 0:
        return message.value
    return f"Windows 音频错误 {code}"


def _check(winmm, code: int, action: str) -> None:
    if code != 0:
        raise AudioPlaybackError(f"{action}失败：{_winmm_error(winmm, code)}")


def play_wav_sync(
    path: str | Path,
    stop_event: threading.Event | None = None,
) -> bool:
    """Play PCM WAV through waveOut and wait, without relying on a GUI thread."""
    if not hasattr(sys, "getwindowsversion"):
        raise AudioPlaybackError("当前播放入口仅支持 Windows")
    audio_format, frames = _read_pcm_wave(path)
    if not frames:
        return True

    winmm = ctypes.WinDLL("winmm")
    winmm.waveOutGetErrorTextW.argtypes = (
        ctypes.c_uint,
        ctypes.c_wchar_p,
        ctypes.c_uint,
    )
    winmm.waveOutGetErrorTextW.restype = ctypes.c_uint
    winmm.waveOutOpen.argtypes = (
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_uint,
        ctypes.POINTER(_WaveFormatEx),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint,
    )
    winmm.waveOutOpen.restype = ctypes.c_uint
    winmm.waveOutPrepareHeader.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(_WaveHeader),
        ctypes.c_uint,
    )
    winmm.waveOutPrepareHeader.restype = ctypes.c_uint
    winmm.waveOutWrite.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(_WaveHeader),
        ctypes.c_uint,
    )
    winmm.waveOutWrite.restype = ctypes.c_uint
    winmm.waveOutReset.argtypes = (ctypes.c_void_p,)
    winmm.waveOutReset.restype = ctypes.c_uint
    winmm.waveOutUnprepareHeader.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(_WaveHeader),
        ctypes.c_uint,
    )
    winmm.waveOutUnprepareHeader.restype = ctypes.c_uint
    winmm.waveOutClose.argtypes = (ctypes.c_void_p,)
    winmm.waveOutClose.restype = ctypes.c_uint

    handle = ctypes.c_void_p()
    _check(
        winmm,
        winmm.waveOutOpen(
            ctypes.byref(handle),
            _WAVE_MAPPER,
            ctypes.byref(audio_format),
            None,
            None,
            _CALLBACK_NULL,
        ),
        "打开扬声器",
    )
    buffer = ctypes.create_string_buffer(frames)
    header = _WaveHeader(
        ctypes.cast(buffer, ctypes.c_void_p),
        len(frames),
        0,
        0,
        0,
        0,
        None,
        0,
    )
    prepared = False
    stopped = False
    try:
        _check(
            winmm,
            winmm.waveOutPrepareHeader(handle, ctypes.byref(header), ctypes.sizeof(header)),
            "准备音频",
        )
        prepared = True
        _check(
            winmm,
            winmm.waveOutWrite(handle, ctypes.byref(header), ctypes.sizeof(header)),
            "播放音频",
        )
        while not (header.dwFlags & _WHDR_DONE):
            if stop_event is not None and stop_event.is_set():
                _check(winmm, winmm.waveOutReset(handle), "停止音频")
                stopped = True
                break
            time.sleep(0.02)
    finally:
        if prepared:
            for _ in range(100):
                result = winmm.waveOutUnprepareHeader(
                    handle, ctypes.byref(header), ctypes.sizeof(header)
                )
                if result != _WAVERR_STILLPLAYING:
                    if result:
                        _check(winmm, result, "释放音频")
                    break
                time.sleep(0.01)
        _check(winmm, winmm.waveOutClose(handle), "关闭扬声器")
    return not stopped
