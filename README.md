# 单词文档配音

面向语言学习者的一键式文档单词配音工具。项目计划从 PDF 中提取单词、音标、释义与例句，为单词或例句生成可播放的语音，并提供适合学习的查看与导出方式。

## 一句话定义

这是一个把“没有配音的单词 PDF”自动转换成“可以逐词试听、检查并导出的有声学习资料”的软件。

它不是普通的整篇 PDF 朗读器。项目重点是识别词表结构，让每个单词、音标、释义、例句和对应语音保持关联，方便学习者针对单个词条反复听读。

## 要解决的问题

语言学习者常常只有静态词汇 PDF。为了听发音，需要手动复制单词、逐个查词典或逐条制作卡片，耗时且容易错配。本项目希望将这一流程缩短为：

1. 导入 PDF；
2. 自动提取并整理词条；
3. 检查少量不确定内容；
4. 一键生成单词或例句语音；
5. 在软件中点读，或导出为后续确定的学习格式。

## 当前状态

v0.1 已形成可试听版本：目标 PDF 的 107 页、4450 条词汇已经通过完整提取回归测试；30 个代表性单词已成功生成本地音频，测试 Anki 卡组和 Windows 便携版均已成功打包。待确认声音后，再批量生成完整 4450 词音频。

## 项目笔记导航

本仓库同时作为 Obsidian 项目知识库使用，根目录文档按“总方案—索引—交接—更新日志”分类：

- [[单词文档配音-完整方案]]：产品范围、架构、流程、验收和后续计划。
- [[单词文档配音方案文档索引]]：所有规格、方案、场景和开发经验的统一入口。
- [[单词文档配音项目交接文档-2026-07-17]]：当前基线、运行路径、验证结果和接手顺序。
- [[更新日志]]：按日期记录用户可感知的新增、修复和仓库调整。

完整产品定义见 [`docs/product-brief.md`](docs/product-brief.md)。当前版本目标、范围和交付标准见 [`spec/current.md`](spec/current.md)。项目目标与约束见 [`docs/goals-and-constraints.md`](docs/goals-and-constraints.md)。

## 仓库结构

- `.obsidian/`：Obsidian 知识库配置；个人窗口状态不进入 Git。
- 根目录中文笔记：完整方案、方案索引、项目交接和更新日志。
- `spec/`：当前版本目标、产品范围和交付规格。
- `assets/`：图片、音频样例、测试文档等资源；使用规则见 `assets/README.md`。
- `docs/`：项目文档；新增文档时必须同步更新 `docs/index.md`。
- `docs/experience-Library/`：已解决问题、复发规则和可复用开发经验。
- `scenes/`：前端审美、页面场景、交互状态和视觉参考。
- `scripts/`：业务逻辑、调试入口、数据处理和测试脚本。
- `src/word_voice/`：PDF 提取、SQLite、语音、桌面界面和 Anki 导出的正式应用代码。
- `tests/`：单元测试与真实 PDF 回归测试。

## 当前可运行入口

开发环境准备：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

启动桌面界面：

```powershell
.\.venv\Scripts\python.exe .\scripts\run_app.py
```

构建无需系统 Python 的 Windows 版本：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1
```

构建结果位于 `dist\WordPdfVoice\WordPdfVoice.exe`。整个 `WordPdfVoice` 文件夹需要一起保留。

当前便携版约 367 MB，包含离线发音模型，因此首次使用和日常发音都不依赖网络。

只运行 PDF 提取：

```powershell
.\.venv\Scripts\python.exe .\scripts\extract_pdf.py "你的词汇.pdf"
```

本地模型、源 PDF、SQLite、音频和 Anki 输出均不会提交到 Git。

## 工作原则

1. 先用真实样本验证，再扩大产品范围。
2. 原始 PDF 只读，所有生成内容输出到独立位置。
3. 本地优先，涉及上传文档或付费接口时必须明确告知用户。
4. 不把非公开、随时可能失效的免费接口作为唯一语音方案。
5. 新增项目文档时同步维护文档索引。
