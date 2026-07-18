# 版本更新与本地数据规则

## v0.2.0 的一次性独立交付

v0.2.0 按用户确认采用独立程序和独立数据：

- v0.1.1 程序保留在 `dist\WordPdfVoice\`；
- v0.2.0 程序保存在 `dist\WordPdfVoice-v0.2.0\`；
- v0.1 数据保存在 `%LOCALAPPDATA%\WordPdfVoice\projects\`；
- v0.2 数据保存在 `%LOCALAPPDATA%\WordPdfVoice\v0.2\projects\`。

v0.2 第一次打开同一个 PDF 时，通过 SQLite 备份接口获取一致性快照，并复制快照中已标记完成的 WAV。复制后的数据库路径全部改为 v0.2 目录，因此两个版本可以独立运行。

## 后续版本规则

从 v0.2.1 开始采用普通升级方式，不再为每次升级复制整套用户数据：

1. 更新 `pyproject.toml`、`src/word_voice/__init__.py` 和窗口标题中的版本信息。
2. 在 `CHANGELOG.md` 和根目录 `更新日志.md` 中写明新增、修复、兼容性和验证结果。
3. 数据结构有变化时执行向前兼容迁移，不按版本复制全部音频。
4. 保留 Git 提交和版本标签作为回退依据；程序目录可以按版本命名，但继续使用同一份兼容数据。
5. 只有用户再次明确要求“并行保留两个可独立运行版本”时，才创建新的版本专用目录。

v0.2.1 在原 `entries` 表自动增加 `audio_profile`，继续使用 `%LOCALAPPDATA%\WordPdfVoice\v0.2\projects\`。v0.2.0 固定默认配置生成的 WAV 可以直接认领；只有用户主动改变声音或语速时，相关词条才重新生成。

## 安全约束

- 升级不得覆盖原始 PDF。
- 数据迁移前必须使用一致性快照或事务，不能直接复制正在写入的 SQLite 文件。
- 已有有效 WAV 不重新生成，除非用户主动更换声音、语速或发音覆盖。
- GitHub 不提交 PDF、SQLite、WAV、`.apkg`、模型或访问令牌。
