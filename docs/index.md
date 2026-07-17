# 项目文档索引

新增、移动或删除 `docs/` 下的文档时，必须同步更新本页。

## 产品与项目

- [产品定义](product-brief.md)：项目是什么、解决什么问题、面向谁以及核心使用流程。
- [v0.1 实施方案](implementation-plan.md)：技术结构、模块边界、实施阶段和本地输出约定。
- [项目目标与约束](goals-and-constraints.md)：产品目标、开发边界、隐私和技术约束。
- [仓库结构](repository-structure.md)：目录职责、文档维护规则和文件放置约定。
- [版本更新与本地数据规则](versioning-and-data.md)：v0.2 独立迁移，以及后续版本采用普通升级的约定。
- [Anki 安装、导入与学习指南](anki-setup-and-usage.md)：当前电脑的卡组配置、每日学习方法、数据位置和后续导入流程。

## 开发经验

- [开发经验库说明](experience-Library/README.md)：问题记录模板和防复发规则。
- [四级词汇 PDF 表格提取规则](experience-Library/2026-07-17-cet4-pdf-extraction.md)：避免长释义导致纯文本顺序错位。
- [Windows SQLite 临时文件被占用](experience-Library/2026-07-17-sqlite-windows-lock.md)：显式关闭数据库连接，避免 WinError 32。
- [Windows eSpeak 无法读取中文安装路径](experience-Library/2026-07-17-espeak-unicode-path.md)：把语音运行时复制到 ASCII 路径。
- [Qt 后台任务启动后没有执行](experience-Library/2026-07-17-qt-worker-lifetime.md)：保持 worker 强引用，避免打包后静默停滞。
- [PyInstaller 漏装依赖包数据](experience-Library/2026-07-18-pyinstaller-package-data.md)：构建后用成品程序生成真实 WAV，防止冻结版缺少 JSON 等运行资源。
- [Anki 教材尖括号标记被隐藏](experience-Library/2026-07-18-anki-html-escaping.md)：导出前转义用户字段，避免 `<古>` 等被当作 HTML。

## 版本规格

版本规格统一保存在仓库根目录的 `spec/` 中：

- [当前版本规格](../spec/current.md)
- [v0.1.1 归档规格](../spec/v0.1.1.md)
