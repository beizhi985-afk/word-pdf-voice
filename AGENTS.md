# Repository Instructions

## Repository root

本文件所在目录是项目唯一仓库根目录。项目文件不得散落到仓库外。

## Required structure

- 根目录保存 Obsidian 导航文档：`README.md`、`单词文档配音-完整方案.md`、`单词文档配音方案文档索引.md`、项目交接文档和 `更新日志.md`。
- `spec/` 保存当前版本目标、范围和可验收的交付规格。
- `assets/` 保存资源文件，并遵守 `assets/README.md`。
- `docs/` 保存项目文档。新增、移动或删除文档时必须更新 `docs/index.md`。
- `docs/experience-Library/` 保存已解决问题、复发规则和开发经验。
- `scenes/` 保存前端审美、交互场景和视觉参考。
- `scripts/` 保存业务逻辑、调试入口和测试脚本。

## Development rules

1. 开始实现前先阅读 `spec/current.md` 和 `docs/goals-and-constraints.md`。
2. 未经明确决定，不扩大当前版本范围。
3. 原始学习文档必须按只读输入处理；不得覆盖用户源文件。
4. 对 PDF 提取、OCR 和语音生成建立可复现的样本测试。
5. 解决具有复发可能的问题后，在 `docs/experience-Library/` 记录现象、原因、修复和防复发规则。
6. 影响用户体验的前端改动应在 `scenes/` 中留下对应场景或说明。
7. 用户可感知的功能变化同时更新 `CHANGELOG.md` 和根目录 `更新日志.md`。
8. 基线、运行路径或下一步发生变化时同步更新根目录项目交接文档。
