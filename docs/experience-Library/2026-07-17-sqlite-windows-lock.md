# Windows SQLite 临时文件被占用

## 现象

测试完成后删除临时目录时报 `WinError 32`，提示 SQLite 数据库仍被另一个进程使用。

## 影响范围

Windows 下的测试清理、项目删除和数据库切换可能失败；长时间运行时还可能积累未关闭连接。

## 根本原因

`sqlite3.Connection` 的上下文管理只负责提交或回滚事务，不保证在退出时关闭连接。依赖垃圾回收在 Windows 上不能及时释放文件句柄。

## 解决办法

为数据层增加统一 `session()` 上下文，显式完成事务并在 `finally` 中关闭连接。所有数据库操作必须经过该入口。

## 验证方式

运行存储测试，退出 `TemporaryDirectory` 时数据库能够立即删除。

## 防复发规则

1. 不直接使用 `with sqlite3.connect(...)` 假设连接会关闭。
2. 新增数据库操作必须使用 `VocabularyStore.session()`。
3. Windows 临时目录清理测试必须保留。
4. 使用 `sqlite3.Connection.backup()` 迁移数据库时，源连接和目标连接都必须通过 `closing()` 显式关闭。

## 相关文件或版本

- `src/word_voice/storage.py`
- `tests/test_core.py`
- v0.1、v0.2 数据迁移

