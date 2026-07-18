# scripts 使用说明

本目录只保存可重复运行的安装、调试和用户入口，正式逻辑位于 `src/word_voice/`。

## 当前入口

- `setup.ps1`：创建虚拟环境、安装依赖并准备本地语音模型。
- `setup_models.py`：从 Kokoro ONNX 官方发布页下载量化模型与声音数据。
- `build.ps1`：构建包含 Python、Qt、本地语音模型、UI 贴纸和小书图标的 `WordPdfVoice-v0.3.1` Windows 独立运行文件夹。
- `verify_portable.py`：调用成品程序生成不同声音、慢速和快速真实 WAV，检查冻结版资源及语音参数是否有效。
- `run_app.py`：启动 Windows 桌面界面。
- `extract_pdf.py`：只执行 PDF 提取并生成 CSV、JSON 与 SQLite。

## 规则

1. 每个入口必须说明输入、输出和运行方式。
2. 默认输出到被 Git 忽略的本地目录，不得覆盖输入文件。
3. 脚本不得包含密钥、个人路径或未经脱敏的用户内容。
4. 对可能产生费用的云端调用提供明确开关；当前版本不使用付费云端语音。
5. 业务规则只能在 `src/word_voice/` 实现，脚本只负责参数和启动。
