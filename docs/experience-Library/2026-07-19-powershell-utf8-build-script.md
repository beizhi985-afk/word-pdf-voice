# Windows PowerShell 5 解析 UTF-8 构建脚本失败

## 现象

`scripts/build.ps1` 在 Windows PowerShell 5 中出现引号未闭合、字符串被截断或不可识别字符，但同一脚本在编辑器中看起来语法正常。

## 原因

Windows PowerShell 5 会把没有 BOM 的 UTF-8 脚本按本地 ANSI 编码读取。脚本中的中文提示经过错误解码后，可能把字符串边界一起破坏，导致构建尚未开始就发生解析错误。

## 已采用修复

- 构建入口中参与 PowerShell 解析的提示文字保持 ASCII，中文结果交给 Python 校验脚本输出。
- 正式构建前先执行 `scripts/verify_version.py`，再进入 PyInstaller。
- 在 Windows PowerShell 5 中实际运行完整构建，不能只依赖编辑器语法高亮。

## 防复发规则

1. 新增 `.ps1` 构建入口时，优先使用 ASCII 控制文字；确需中文时明确保存为带 BOM 的 UTF-8。
2. 修改构建脚本后必须用项目实际采用的 Windows PowerShell 版本运行一次。
3. 解析失败时先检查文件编码和引号边界，不要直接归因于 PyInstaller 或 Python。

