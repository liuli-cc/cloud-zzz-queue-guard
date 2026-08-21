# 云·绝区零排队提醒

实时监测云·绝区零的排队状态：客户端启动后自动开始监测，客户端退出后自动停止。排队成功时，只要电脑有网络连接，就会播放系统提示音并提示“云绝区零排队成功”。

支持 macOS 和 Windows 两个平台，均可直接下载运行，不需要安装 Python 或其他依赖。

## 直接下载

所有安装包都放在 GitHub Releases：

<https://github.com/liuli-cc/cloud-zzz-queue-guard/releases>

### macOS 使用方法

1. 下载 `CloudZZZQueueMonitor-macOS.zip`。
2. 解压后把 `CloudZZZQueueMonitor.app` 拖到“应用程序”文件夹。
3. 首次打开如果被 macOS 拦截，右键点击 App，选择“打开”，再点一次“打开”。
4. 在源码目录执行一次 `./install.sh`，安装 macOS 后台进程监测器；之后云·绝区零启动时自动拉起 App，退出时自动关闭 App。屏幕顶部只显示前方排队人数和预计等待时间。

如果 Codex 的 TokenLens 灵动岛同时运行，绝区零灵动岛会自动放在 Codex 岛左侧；如果 Codex 未运行，则显示在屏幕顶部中央。

macOS 的日志和配置保存在：

```text
~/Library/Application Support/CloudZZZQueueMonitor
```

### Windows 使用方法

1. 下载 `CloudZZZQueueMonitor.exe`。
2. 双击运行。如果 Windows SmartScreen 提示，点击“更多信息”，再选择“仍要运行”。
3. 打开云·绝区零后，排队窗口会自动显示排队状态。

Windows 的日志和配置默认保存在 EXE 同目录；如果该目录不可写，会改用 `%LOCALAPPDATA%\CloudZZZQueueMonitor`。

## 找不到排队日志时

程序会优先使用自动检测到的客户端日志数据库。如果显示“未找到云绝区零排队日志数据库”，可以手动指定：

- macOS：在 `~/Library/Application Support/CloudZZZQueueMonitor/config.json` 中填写 `log_db_path`
- Windows：在 EXE 同目录的 `config.json` 中填写 `log_db_path`

配置示例见 `config.example.json`。

## 可选：仅热点提醒

默认版本不要求热点，只要有网络就会提醒。如果希望改成“只有手机热点才提醒”，可以在配置文件中把 `require_hotspot` 设为 `true`。此时程序优先使用默认网关判断，默认把以下常见手机热点网段视为热点：

- `172.20.10.1`，常见于 iPhone 个人热点
- `192.168.43.1`，常见于 Android 热点
- `192.168.137.1`，常见于 Windows 移动热点
- `192.168.42.129`，常见于 Android USB/热点

如果热点网关不同，编辑配置文件中的 `hotspot_gateways` 或 `hotspot_gateway_prefixes`。

## 源码方式使用

仓库里的 `cloud_zzz_queue_guard.py`、`QueueWindow.swift` 相关源码主要供开发使用。Windows 版本仍由 `cloud_zzz_queue_guard_gui.py` 提供窗口；macOS 发布包使用原生 Swift 灵动岛，并在 App 内携带后台监测核心。GitHub Actions 会自动生成 macOS App 和 Windows EXE。
