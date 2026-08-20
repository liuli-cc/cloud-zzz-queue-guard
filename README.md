# 云·绝区零排队提醒

这个目录里是一个 macOS 后台监测程序。它会跟着 `/Applications/云·绝区零.app` 的启动和退出自动切换监测状态，实时读取客户端自己写入的排队日志；当检测到排队成功，并且电脑当前默认网络被判断为手机热点时，会播放系统提示音并朗读“云绝区零排队成功”。

## 安装

```bash
cd /Users/liuli/内蒙古师范大学/云绝区零排队提醒
chmod +x install.sh uninstall.sh status.sh
./install.sh
```

安装后程序会作为当前用户的 LaunchAgent 常驻运行，不用手动打开终端。

## 排队窗口

运行下面的命令会编译并打开一个桌面窗口，每秒读取后台状态文件，实时显示客户端状态、排队人数、预计等待、当前网络和提醒状态：

```bash
cd /Users/liuli/内蒙古师范大学/云绝区零排队提醒
./build_window.sh
```

窗口源码在 `QueueWindow.swift`。下次想重新打开窗口时，直接双击 `云绝区零排队提醒.app` 即可。

## 查看状态

```bash
cd /Users/liuli/内蒙古师范大学/云绝区零排队提醒
./status.sh
```

也可以看日志：

```bash
tail -f /Users/liuli/内蒙古师范大学/云绝区零排队提醒/logs/guard.log
```

## 测试

测试当前网络是否被判定为热点：

```bash
./cloud_zzz_queue_guard.py --test-network
```

测试排队日志解析（云·绝区零打开且正在排队时最有意义）：

```bash
./cloud_zzz_queue_guard.py --test-log
```

## 热点判断规则

macOS 26 会把当前 Wi-Fi 名称显示为 `<redacted>`，所以程序不依赖 SSID，优先使用默认路由的网关判断。默认把以下常见手机热点网段视为热点：

- `172.20.10.1`，常见于 iPhone 个人热点
- `192.168.43.1`，常见于 Android 热点
- `192.168.137.1`，常见于 Windows 移动热点
- `192.168.42.129`，常见于 Android USB/热点

如果你的热点网关不同，编辑 `config.json` 里的 `hotspot_gateways` 或 `hotspot_gateway_prefixes`，然后重新运行 `./install.sh`。

## 卸载

```bash
cd /Users/liuli/内蒙古师范大学/云绝区零排队提醒
./uninstall.sh
```
