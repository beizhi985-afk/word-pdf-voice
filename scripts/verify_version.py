from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    init_text = (root / "src" / "word_voice" / "__init__.py").read_text(encoding="utf-8")
    package_version = re.search(r'__version__\s*=\s*"([^"]+)"', init_text)
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    spec_text = (root / "packaging" / "word_voice.spec").read_text(encoding="utf-8")
    spec_version = re.search(r'app_name\s*=\s*"WordPdfVoice-v([^"]+)"', spec_text)
    build_text = (root / "scripts" / "build.ps1").read_text(encoding="utf-8")
    build_version = re.search(r'dist\\WordPdfVoice-v([^\\]+)\\WordPdfVoice-v[^\\]+\.exe', build_text)
    versions = {
        "源码": package_version.group(1) if package_version else "缺失",
        "pyproject": str(pyproject["project"]["version"]),
        "PyInstaller": spec_version.group(1) if spec_version else "缺失",
        "构建结果": build_version.group(1) if build_version else "缺失",
    }
    if len(set(versions.values())) != 1:
        print("版本号不一致：" + "，".join(f"{key}={value}" for key, value in versions.items()))
        return 1
    print(f"版本号一致：v{next(iter(versions.values()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
