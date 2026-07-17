# 项目文档索引

新增、移动或删除 `docs/` 下的文档时，必须同步更新本页。

## 产品与项目

- [产品定义](product-brief.md)：项目是什么、解决什么问题、面向谁以及核心使用流程。
- [v0.1 实施方案](implementation-plan.md)：技术结构、模块边界、实施阶段和本地输出约定。
- [项目目标与约束](goals-and-constraints.md)：产品目标、开发边界、隐私和技术约束。
- [仓库结构](repository-structure.md)：目录职责、文档维护规则和文件放置约定。

## 开发经验

- [开发经验库说明](experience-Library/README.md)：问题记录模板和防复发规则。
- [四级词汇 PDF 表格提取规则](experience-Library/2026-07-17-cet4-pdf-extraction.md)：避免长释义导致纯文本顺序错位。
- [Windows SQLite 临时文件被占用](experience-Library/2026-07-17-sqlite-windows-lock.md)：显式关闭数据库连接，避免 WinError 32。
- [Windows eSpeak 无法读取中文安装路径](experience-Library/2026-07-17-espeak-unicode-path.md)：把语音运行时复制到 ASCII 路径。

## 版本规格

版本规格统一保存在仓库根目录的 `spec/` 中：

- [当前版本规格](../spec/current.md)
