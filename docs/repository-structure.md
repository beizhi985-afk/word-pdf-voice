# 仓库结构

```text
单词翻译/
├─ .obsidian/
│  ├─ app.json
│  ├─ appearance.json
│  └─ core-plugins.json
├─ AGENTS.md
├─ CHANGELOG.md
├─ README.md
├─ 单词文档配音-完整方案.md
├─ 单词文档配音方案文档索引.md
├─ 单词文档配音项目交接文档-2026-07-17.md
├─ 更新日志.md
├─ pyproject.toml
├─ spec/
│  └─ current.md
├─ assets/
│  └─ README.md
├─ docs/
│  ├─ index.md
│  ├─ product-brief.md
│  ├─ implementation-plan.md
│  ├─ goals-and-constraints.md
│  ├─ repository-structure.md
│  └─ experience-Library/
├─ scenes/
│  ├─ README.md
│  └─ v0.1-desktop.md
├─ src/
│  └─ word_voice/
│     ├─ extractor.py
│     ├─ storage.py
│     ├─ tts.py
│     ├─ anki_export.py
│     ├─ app.py
│     └─ cli.py
├─ scripts/
│  ├─ setup.ps1
│  ├─ setup_models.py
│  ├─ build.ps1
│  ├─ verify_portable.py
│  ├─ run_app.py
│  └─ extract_pdf.py
├─ packaging/
│  └─ word_voice.spec
└─ tests/
   ├─ test_app_worker.py
   ├─ test_core.py
   ├─ test_anki_export.py
   ├─ test_packaging.py
   └─ test_real_pdf.py
```

## 目录职责

### 根目录项目笔记

参考 Obsidian 项目仓库的分类方式，根目录用中文笔记提供“首页、完整方案、文档索引、项目交接、更新日志”五类入口。软件的正式规格和细分经验仍保存在对应工程目录，根目录笔记负责导航和当前状态汇总。

### `.obsidian/`

保存通用知识库配置。`workspace.json` 属于个人窗口状态并被 Git 忽略，避免每次打开仓库都产生无意义变更。

### `spec/`

只描述当前版本做什么、不做什么、交付什么以及如何验收。范围变化必须先更新规格，再实现功能。

### `assets/`

保存可进入版本控制的资源和最小测试样本。详细规则见 `assets/README.md`。受版权保护的目标 PDF 不进入仓库。

### `docs/`

保存产品、技术、决策和使用文档。新增、移动或删除文档时必须同步更新 `docs/index.md`。

### `docs/experience-Library/`

记录已经解决且可能复发的问题。每条经验应包含现象、原因、解决办法、验证方式和防复发规则。

### `scenes/`

保存页面场景、审美方向、组件状态、交互流程和视觉参考。代码实现前应先明确关键使用场景。

### `src/word_voice/`

正式应用代码。提取、存储、语音、导出和界面分层，避免 UI 直接承载解析规则。

### `scripts/`

保存安装、模型准备、调试和运行入口。正式业务逻辑应调用 `src/word_voice/`，不在脚本中重复实现。

### `packaging/`

保存 Windows 独立运行版本的 PyInstaller 配置。模型仅在本地构建时加入成品，不进入 Git。

### `tests/`

保存不依赖用户文档的单元测试，以及通过环境变量启用的真实 PDF 回归测试。

### 本地生成目录

`.venv/`、`models/`、`output/`、音频、数据库和 `.apkg` 均被 Git 忽略，不属于仓库源码。
