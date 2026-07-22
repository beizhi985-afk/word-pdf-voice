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
- [语音设置变化但仍播放旧缓存](experience-Library/2026-07-18-tts-profile-cache.md)：把声音、语速和语言纳入缓存配置，避免继续播放旧 WAV。
- [SQLite 版本迁移、自动备份与可恢复替换](experience-Library/2026-07-19-sqlite-backup-and-recovery.md)：迁移前一致性快照、每日备份、完整性检查和原子恢复规则。
- [Windows PowerShell 5 解析 UTF-8 构建脚本失败](experience-Library/2026-07-19-powershell-utf8-build-script.md)：避免无 BOM 中文脚本破坏字符串边界，并要求用实际 PowerShell 完整构建。
- [复杂双栏中英 PDF 无法导入](experience-Library/2026-07-22-complex-bilingual-pdf.md)：分级解析、坐标分栏、预览确认和 OCR 边界。
- [连续播放英文和中文静默无声](experience-Library/2026-07-22-continuous-playback-audio.md)：统一 waveOut 播放、中文先生成 WAV，以及正式包声音门禁。

## 版本规格

版本规格统一保存在仓库根目录的 `spec/` 中：

- [当前版本规格](../spec/current.md)
- [v0.1.1 归档规格](../spec/v0.1.1.md)
