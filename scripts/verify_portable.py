from __future__ import annotations

import argparse
import subprocess
import tempfile
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def verify(executable: Path) -> Path:
    if not executable.is_file():
        raise FileNotFoundError(f"找不到便携版程序：{executable}")
    with tempfile.TemporaryDirectory(prefix="word-pdf-voice-smoke-") as directory:
        output = Path(directory) / "portable-smoke.wav"
        error_file = output.with_suffix(output.suffix + ".error.txt")
        result = subprocess.run(
            [str(executable), "--smoke-tts", str(output)],
            capture_output=True,
            timeout=180,
            check=False,
        )
        if result.returncode != 0 or not output.is_file():
            detail = error_file.read_text(encoding="utf-8") if error_file.is_file() else "无错误文件"
            raise RuntimeError(f"便携版真实发音失败（退出码 {result.returncode}）：\n{detail}")
        with wave.open(str(output), "rb") as audio:
            if audio.getnchannels() != 1:
                raise RuntimeError(f"声道数异常：{audio.getnchannels()}")
            if audio.getframerate() != 24000:
                raise RuntimeError(f"采样率异常：{audio.getframerate()}")
            if audio.getnframes() <= 0:
                raise RuntimeError("生成的 WAV 没有音频帧")
        return executable


def main() -> int:
    parser = argparse.ArgumentParser(description="验证打包版能否生成真实 WAV")
    parser.add_argument(
        "--exe",
        type=Path,
        default=ROOT / "dist" / "WordPdfVoice" / "WordPdfVoice.exe",
    )
    arguments = parser.parse_args()
    result = verify(arguments.exe.resolve())
    print(f"便携版真实发音验证通过：{result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
