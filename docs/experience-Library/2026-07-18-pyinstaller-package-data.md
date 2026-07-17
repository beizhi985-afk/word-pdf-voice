# PyInstaller 漏装依赖包的数据文件

## 现象

便携版可以启动、分析 PDF 和显示词表，但“试听所选”报错，生成 30 词时全部失败。错误指向：

```text
_internal\language_tags\data\json\index.json
```

## 根因

`kokoro-onnx` 通过 `phonemizer-fork → segments → csvw → language-tags` 间接使用语言标签数据库。PyInstaller 自动发现了 Python 模块，却没有自动收集 `language_tags/data/json/` 下的非 Python 数据文件。此前打包验收只检查程序能否启动，未让成品真正生成语音，因此没有发现资源缺失。

## 修复

- 在 PyInstaller 规格中对 `language_tags` 使用 `collect_all()`。
- 为应用增加仅供构建验证使用的 `--smoke-tts` 入口。
- 构建结束后由 `scripts/verify_portable.py` 调用成品程序生成真实 WAV，并校验单声道、24 kHz 和非空音频帧。
- 真实发音验证失败时，整个构建直接失败。

## 防复发规则

包含模型、词典、JSON、模板或共享数据的依赖不能只做“程序启动”验收。冻结版发布前必须至少执行一次穿过真实依赖链的最小业务操作；本项目的最低标准是用成品程序生成一个真实单词 WAV。
