# 奶蛙快传 · Naifrog Transfer

手机与 Windows 电脑之间的局域网双向文件、照片和文字传输工具。电脑启动后，在浏览器显示二维码；手机扫码即可使用，无需安装手机应用。

当前版本：**v1.7**。项目使用 Python 标准库 HTTP 服务与原生 HTML/CSS/JavaScript，不需要 Node.js 或云端服务器。

## 功能

- 手机 → 电脑：支持多文件、图片、文字和链接。
- 电脑 → 手机：支持文件和文字，手机手动点击下载；文件下载支持 Range 请求。
- 接收成功后自动保存到程序旁的 `收到的文件` 文件夹，结束后保留，重启恢复最近最多 300 条记录。
- 保存名包含时间与随机编号，降低同名冲突风险。
- 电脑端图片预览、系统应用打开、复制文字、打开接收文件夹。
- 发送缓存使用系统临时目录，正常结束后清理，不在桌面生成随机临时文件夹。
- 附有 Windows 无线投屏设置入口；实际投屏由 Windows / Miracast 提供，不是网页传输功能。HarmonyOS 真机兼容性仍需验证。

## 环境与启动

主要目标平台是 Windows 10 / 11。推荐使用 Python 3.14（当前打包环境为 3.14.4）；其他 Python 版本尚未完整验证。

在项目根目录打开 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

程序自动打开电脑管理页面。手机与电脑连接同一 Wi-Fi，点击欢迎页入口后扫描当前二维码。没有浏览器界面时可运行 `python app.py --headless`，终端会输出本机管理地址。

**不能直接双击 `ui.html` 使用**，必须启动 `app.py` 或打包后的 EXE。管理页面地址包含本次会话的管理凭据，不要分享；分享给手机的是页面里的二维码 / 手机连接地址。

## 保存位置

源码运行时：`app.py` 同级的 `收到的文件`。

EXE 运行时：EXE 同级的 `收到的文件`。如果把 EXE 放在桌面，接收文件夹也会位于桌面；请把程序放在可写目录。复制文字也会作为文本文件自动保存。临时发送内容在退出后不可继续下载。

## 手机连不上时

1. 保持电脑程序运行，手机和电脑连接同一局域网，使用最新二维码。换网络后重新启动程序并重新扫码，旧 IP 和旧会话链接可能失效。
2. Windows 防火墙提示时，允许该程序在你信任的网络接收连接。程序会在 TCP `17960–17979` 中选择一个可用端口。
3. 换 EXE 路径或重新打包后，旧路径的防火墙放行规则可能不适用。检查是否存在针对当前程序的阻止规则；不建议关闭整个防火墙。
4. 多网卡时在页面选择正确的 Wi-Fi / 热点 IP，`127.0.0.1` 只供电脑自身访问。
5. 校园网、企业网或公共 Wi-Fi 可能隔离设备；可尝试手机开热点并让电脑连接。代理或 VPN 也可能影响局域网访问。
6. 关闭网页不会停止后台服务。使用页面的“结束接收”，避免反复启动造成多个实例。

这些步骤不代表所有网络环境已完成真机验证。

## 打包 Windows EXE

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts/build.py
```

输出位于 `dist/奶蛙快传双向版.exe`。构建脚本使用项目相对位置，可以在其他电脑和目录运行。构建依赖固定为当前使用的版本；不承诺字节级可重复构建。源码包不包含 EXE，可自行构建后放到 GitHub Releases。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试覆盖文件与文字持久化、同名接收、会话缓存清理、记录恢复、访问控制与中断清理。测试使用模拟 HTTP 处理器，不代表真实手机网络端到端测试。GitHub Actions 在 Windows / Python 3.14 上运行测试。

## 安全与已知限制

- 仅供可信局域网使用，采用 HTTP，没有 TLS 加密。不要直接暴露到公网或设置路由器端口映射。
- 每次启动生成随机会话凭据；持有手机连接链接的设备可以向电脑发送内容，并查看本次发送给手机的内容。没有逐设备配对、逐次确认或速率限制。
- 单个文件上传上限 2 GiB；文字请求上限 1 MiB。大量文件仍可能耗尽磁盘。
- 上传成功后自动保存，使用者应自行检查接收内容。管理员打开文件调用 Windows 默认应用。
- 当前不支持自动发现、跨公网中转、单实例锁定或运行中自动更新网络地址。
- 项目未经过完整安全审计，系统投屏兼容性依赖硬件与系统。

## 上传 GitHub

1. 新建空仓库，例如 `naifrog-transfer`。
2. **解压源码 ZIP，上传里面的项目文件**；不要只把 ZIP 当作源码上传，也不要上传整个本机运行目录。
3. 确保仓库根目录直接包含 `README.md`、`app.py`、`ui.html` 和 `LICENSE`。启用显示隐藏文件以便一并上传 `.github`、`.gitignore`、`.gitattributes`。
4. 通过网页或 Git 提交。若另发 EXE，请放到 Releases。

使用 Git 时，也可在解压目录执行：

```powershell
git init
git add .
git commit -m "Initial open-source release v1.7"
git branch -M main
# 用你的实际仓库地址替换下面的占位符
git remote add origin https://github.com/YOUR_USERNAME/naifrog-transfer.git
git push -u origin main
```

`.gitignore` 排除了接收文件、日志、缓存、虚拟环境及构建产物。上传前仍应检查暂存文件列表。

## 许可

本项目源码默认按 MIT 许可证发布，见 [LICENSE](LICENSE)。第三方依赖遵循各自许可证；[THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt) 保留原 Windows 发行环境附带的许可信息，其中包含可能由打包环境收集的可选组件。重新分发 EXE 时请随附该文件；若构建环境或依赖发生变化，应重新核对相应许可。
