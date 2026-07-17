# Windows eSpeak 无法读取中文安装路径

## 现象

Kokoro ONNX 首次生成时报错，eSpeak 尝试读取不存在的构建机路径，或者把包含中文的项目路径显示成乱码。

## 影响范围

当虚拟环境或应用位于含中文字符的目录时，英语音素转换可能无法初始化。本项目的目标仓库路径本身包含中文，因此必须处理。

## 根本原因

Windows 版 eSpeak 数据初始化对非 ASCII 路径兼容不稳定；依赖包内的 DLL 和 `espeak-ng-data` 位于中文路径时可能被错误编码。

## 解决办法

语音引擎首次启动时，把 eSpeak DLL 和数据目录复制到 `%LOCALAPPDATA%\WordPdfVoice\runtime\espeakng`，再通过 `EspeakConfig` 显式传入这个 ASCII 路径。模型和用户数据仍可保留在中文目录。

## 验证方式

在包含中文目录名的仓库和虚拟环境中生成至少一个英文单词 WAV，并检查文件可播放。

## 防复发规则

1. Windows 下不得直接依赖 `espeakng_loader` 返回的包内中文路径。
2. eSpeak 运行时目录必须固定在本地应用数据的 ASCII 子目录。
3. 模型升级后保留单词生成冒烟测试。

## 相关文件或版本

- `src/word_voice/tts.py`
- v0.1

