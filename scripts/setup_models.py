from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path


BASE_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
FILES = {
    "kokoro-v1.0.int8.onnx": f"{BASE_URL}/kokoro-v1.0.int8.onnx",
    "voices-v1.0.bin": f"{BASE_URL}/voices-v1.0.bin",
}


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")

    last_percent = -1

    def report(blocks: int, block_size: int, total_size: int) -> None:
        nonlocal last_percent
        downloaded = blocks * block_size
        percent = int(min(100, downloaded / total_size * 100)) if total_size > 0 else 0
        if percent != last_percent:
            last_percent = percent
            print(f"\r{destination.name}: {percent:3d}%", end="", flush=True)

    urllib.request.urlretrieve(url, temporary, reporthook=report)
    print()
    temporary.replace(destination)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="下载 Kokoro ONNX 本地语音模型")
    parser.add_argument(
        "--model-dir",
        default=str(Path(__file__).resolve().parents[1] / "models"),
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    model_dir = Path(args.model_dir).expanduser().resolve()
    for filename, url in FILES.items():
        destination = model_dir / filename
        if destination.is_file() and not args.force:
            print(f"已存在：{destination}")
            continue
        print(f"正在下载 {filename}...")
        try:
            download(url, destination)
        except Exception as exc:
            print(f"下载失败：{exc}", file=sys.stderr)
            return 1
    print(f"模型已准备：{model_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
