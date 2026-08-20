import Cocoa

func hexColor(_ value: UInt32) -> NSColor {
    NSColor(
        srgbRed: CGFloat((value >> 16) & 0xFF) / 255.0,
        green: CGFloat((value >> 8) & 0xFF) / 255.0,
        blue: CGFloat(value & 0xFF) / 255.0,
        alpha: 1.0
    )
}

func makeLabel(
    size: CGFloat,
    weight: NSFont.Weight,
    color: NSColor,
    alignment: NSTextAlignment = .left
) -> NSTextField {
    let label = NSTextField(labelWithString: "")
    label.font = NSFont.systemFont(ofSize: size, weight: weight)
    label.textColor = color
    label.alignment = alignment
    label.lineBreakMode = .byWordWrapping
    label.maximumNumberOfLines = 2
    return label
}

final class CardView: NSView {
    init(frame: NSRect, fill: NSColor) {
        super.init(frame: frame)
        wantsLayer = true
        layer?.backgroundColor = fill.cgColor
        layer?.cornerRadius = 8
        layer?.masksToBounds = true
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
}

final class StatusPill: NSView {
    let label = makeLabel(size: 13, weight: .semibold, color: .white, alignment: .center)

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        layer?.cornerRadius = frame.height / 2
        label.frame = bounds
        addSubview(label)
        label.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            label.centerXAnchor.constraint(equalTo: centerXAnchor),
            label.centerYAnchor.constraint(equalTo: centerYAnchor),
            label.widthAnchor.constraint(equalTo: widthAnchor, constant: -12),
        ])
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func set(text: String, color: NSColor) {
        label.stringValue = text
        layer?.backgroundColor = color.cgColor
    }
}

final class DashboardView: NSView {
    private let titleLabel = makeLabel(size: 22, weight: .bold, color: hexColor(0x111827))
    private let appPill = StatusPill(frame: NSRect(x: 0, y: 0, width: 126, height: 30))
    private let queueState = makeLabel(size: 30, weight: .bold, color: hexColor(0x111827))
    private let queueDetail = makeLabel(size: 14, weight: .regular, color: hexColor(0x6B7280))

    private let rankTitle = makeLabel(size: 12, weight: .medium, color: hexColor(0x6B7280))
    private let rankValue = makeLabel(size: 26, weight: .bold, color: hexColor(0x111827), alignment: .center)
    private let lengthTitle = makeLabel(size: 12, weight: .medium, color: hexColor(0x6B7280))
    private let lengthValue = makeLabel(size: 26, weight: .bold, color: hexColor(0x111827), alignment: .center)
    private let waitTitle = makeLabel(size: 12, weight: .medium, color: hexColor(0x6B7280))
    private let waitValue = makeLabel(size: 26, weight: .bold, color: hexColor(0x111827), alignment: .center)

    private let networkTitle = makeLabel(size: 12, weight: .medium, color: hexColor(0x6B7280))
    private let networkValue = makeLabel(size: 18, weight: .semibold, color: hexColor(0x111827))
    private let gatewayValue = makeLabel(size: 13, weight: .regular, color: hexColor(0x6B7280))

    private let alertTitle = makeLabel(size: 12, weight: .medium, color: hexColor(0x6B7280))
    private let alertValue = makeLabel(size: 14, weight: .regular, color: hexColor(0x111827))
    private let updatedValue = makeLabel(size: 13, weight: .regular, color: hexColor(0x9CA3AF), alignment: .right)

    private let formatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm:ss"
        return formatter
    }()

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.backgroundColor = hexColor(0xF3F6F9).cgColor
        buildLayout()
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    private func buildLayout() {
        titleLabel.stringValue = "云·绝区零排队监测"
        titleLabel.frame = NSRect(x: 24, y: 452, width: 300, height: 34)
        addSubview(titleLabel)

        appPill.frame = NSRect(x: 310, y: 454, width: 126, height: 30)
        addSubview(appPill)

        let queueCard = CardView(frame: NSRect(x: 20, y: 360, width: 420, height: 80), fill: .white)
        addSubview(queueCard)
        queueState.frame = NSRect(x: 36, y: 386, width: 250, height: 38)
        queueCard.addSubview(queueState)
        queueDetail.frame = NSRect(x: 36, y: 368, width: 388, height: 20)
        queueCard.addSubview(queueDetail)

        let rankCard = CardView(frame: NSRect(x: 20, y: 268, width: 132, height: 84), fill: .white)
        let lengthCard = CardView(frame: NSRect(x: 164, y: 268, width: 132, height: 84), fill: .white)
        let waitCard = CardView(frame: NSRect(x: 308, y: 268, width: 132, height: 84), fill: .white)
        addSubview(rankCard)
        addSubview(lengthCard)
        addSubview(waitCard)

        rankTitle.stringValue = "前方人数"
        rankTitle.frame = NSRect(x: 24, y: 314, width: 124, height: 16)
        rankValue.frame = NSRect(x: 24, y: 280, width: 124, height: 32)
        rankCard.addSubview(rankTitle)
        rankCard.addSubview(rankValue)

        lengthTitle.stringValue = "总排队人数"
        lengthTitle.frame = NSRect(x: 168, y: 314, width: 124, height: 16)
        lengthValue.frame = NSRect(x: 168, y: 280, width: 124, height: 32)
        lengthCard.addSubview(lengthTitle)
        lengthCard.addSubview(lengthValue)

        waitTitle.stringValue = "预计等待"
        waitTitle.frame = NSRect(x: 312, y: 314, width: 124, height: 16)
        waitValue.frame = NSRect(x: 312, y: 280, width: 124, height: 32)
        waitCard.addSubview(waitTitle)
        waitCard.addSubview(waitValue)

        let networkCard = CardView(frame: NSRect(x: 20, y: 178, width: 420, height: 78), fill: .white)
        addSubview(networkCard)
        networkTitle.stringValue = "当前网络"
        networkTitle.frame = NSRect(x: 36, y: 226, width: 388, height: 16)
        networkValue.frame = NSRect(x: 36, y: 196, width: 220, height: 24)
        gatewayValue.frame = NSRect(x: 250, y: 196, width: 174, height: 20)
        networkCard.addSubview(networkTitle)
        networkCard.addSubview(networkValue)
        networkCard.addSubview(gatewayValue)

        let alertCard = CardView(frame: NSRect(x: 20, y: 88, width: 420, height: 78), fill: .white)
        addSubview(alertCard)
        alertTitle.stringValue = "提醒状态"
        alertTitle.frame = NSRect(x: 36, y: 136, width: 220, height: 16)
        alertValue.frame = NSRect(x: 36, y: 106, width: 260, height: 20)
        updatedValue.frame = NSRect(x: 300, y: 106, width: 124, height: 18)
        alertCard.addSubview(alertTitle)
        alertCard.addSubview(alertValue)
        alertCard.addSubview(updatedValue)
    }

    func update(with status: [String: Any]?) {
        guard let status = status else {
            appPill.set(text: "未运行", color: hexColor(0x9CA3AF))
            queueState.stringValue = "等待数据"
            queueDetail.stringValue = "后台程序尚未写入状态"
            rankValue.stringValue = "—"
            lengthValue.stringValue = "—"
            waitValue.stringValue = "—"
            networkValue.stringValue = "尚未获取"
            gatewayValue.stringValue = ""
            alertValue.stringValue = "等待排队"
            updatedValue.stringValue = ""
            return
        }

        let appRunning = status["app_running"] as? Bool ?? false
        appPill.set(text: appRunning ? "运行中" : "未运行", color: appRunning ? hexColor(0x10B981) : hexColor(0x9CA3AF))

        let state = status["queue_state"] as? String ?? "未知"
        queueState.stringValue = state
        switch state {
        case "排队中":
            queueState.textColor = hexColor(0xD97706)
            queueDetail.stringValue = "正在排队，耐心等待进入"
        case "排队成功":
            queueState.textColor = hexColor(0x059669)
            queueDetail.stringValue = "已进入游戏，可以开始游玩"
        case "等待排队日志":
            queueState.textColor = hexColor(0x2563EB)
            queueDetail.stringValue = "等待客户端写入排队信息"
        default:
            queueState.textColor = hexColor(0x111827)
            queueDetail.stringValue = "当前没有排队任务"
        }

        let queue = (status["last_queue"] as? [String: Any]) ?? [:]
        rankValue.stringValue = displayInt(queue["queue_rank"])
        lengthValue.stringValue = displayInt(queue["queue_length"])
        waitValue.stringValue = displayMinutes(queue["waiting_time_min"])

        if let network = status["current_network"] as? [String: Any] {
            let hotspot = network["hotspot"] as? Bool ?? false
            networkValue.stringValue = hotspot ? "手机热点" : "Wi-Fi / 其他网络"
            networkValue.textColor = hotspot ? hexColor(0x059669) : hexColor(0x2563EB)
            gatewayValue.stringValue = "网关 \(network["gateway"] as? String ?? "—")"
        } else {
            networkValue.stringValue = "尚未获取"
            networkValue.textColor = hexColor(0x6B7280)
            gatewayValue.stringValue = ""
        }

        if let alert = status["last_alert"] as? [String: Any] {
            let reason = alert["reason"] as? String ?? ""
            if reason == "queue_success_on_hotspot" {
                alertValue.stringValue = "排队成功，已播放提醒声音"
                alertValue.textColor = hexColor(0x059669)
            } else if reason == "queue_success_but_not_hotspot" {
                alertValue.stringValue = "排队成功，非热点未播放声音"
                alertValue.textColor = hexColor(0x6B7280)
            } else {
                alertValue.stringValue = "排队成功，已提醒"
                alertValue.textColor = hexColor(0x059669)
            }
        } else {
            alertValue.stringValue = "等待排队成功"
            alertValue.textColor = hexColor(0x6B7280)
        }

        if let updated = status["updated_at"] as? Double {
            updatedValue.stringValue = formatter.string(from: Date(timeIntervalSince1970: updated))
        } else {
            updatedValue.stringValue = ""
        }
    }

    private func displayInt(_ value: Any?) -> String {
        if let number = value as? NSNumber {
            return number.stringValue
        }
        if let text = value as? String {
            return text
        }
        return "—"
    }

    private func displayMinutes(_ value: Any?) -> String {
        if let number = value as? NSNumber {
            return String(format: "%.1f 分", number.doubleValue)
        }
        if let text = value as? String, let number = Double(text) {
            return String(format: "%.1f 分", number)
        }
        return "—"
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var window: NSWindow?
    private var dashboard: DashboardView?
    private var timer: Timer?
    private var statusURL: URL?

    func applicationDidFinishLaunching(_ notification: Notification) {
        statusURL = locateStatusFile()

        let contentRect = NSRect(x: 0, y: 0, width: 460, height: 500)
        let window = NSWindow(
            contentRect: contentRect,
            styleMask: [.titled, .closable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        window.title = "云·绝区零排队监测"
        window.isReleasedWhenClosed = false
        window.setContentSize(contentRect.size)

        let dashboard = DashboardView(frame: NSRect(origin: .zero, size: contentRect.size))
        window.contentView = dashboard
        self.window = window
        self.dashboard = dashboard

        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            self?.refresh()
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    private func locateStatusFile() -> URL? {
        let executable = URL(fileURLWithPath: CommandLine.arguments[0])
        var directory = executable.deletingLastPathComponent()
        for _ in 0..<8 {
            let candidate = directory.appendingPathComponent("state/status.json")
            if FileManager.default.fileExists(atPath: candidate.path) {
                return candidate
            }
            directory = directory.deletingLastPathComponent()
        }
        return URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("state/status.json")
    }

    private func refresh() {
        guard let url = statusURL else { return }
        guard let data = try? Data(contentsOf: url),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            dashboard?.update(with: nil)
            return
        }
        dashboard?.update(with: object)
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
