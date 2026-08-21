import AppKit
import Foundation
import SwiftUI

struct QueueSnapshot: Equatable {
    var appRunning = false
    var queueState = "未运行"
    var queueLength: Int?
    var queueRank: Int?
    var waitingTimeMinutes: Double?
    var logError: String?
}

@MainActor
final class QueueStatusStore: ObservableObject {
    @Published var snapshot = QueueSnapshot()

    private var refreshTimer: Timer?
    private let configuredStateURL: URL?

    init() {
        if let index = CommandLine.arguments.firstIndex(of: "--state-file"),
           index + 1 < CommandLine.arguments.count {
            configuredStateURL = URL(fileURLWithPath: CommandLine.arguments[index + 1]).standardizedFileURL
        } else {
            configuredStateURL = nil
        }
    }

    private var stateURL: URL {
        if let configuredStateURL {
            return configuredStateURL
        }
        return FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("CloudZZZQueueMonitor", isDirectory: true)
            .appendingPathComponent("state", isDirectory: true)
            .appendingPathComponent("status.json")
    }

    func start() {
        refresh()
        let timer = Timer(timeInterval: 0.5, target: self, selector: #selector(refreshTimerFired), userInfo: nil, repeats: true)
        refreshTimer = timer
        RunLoop.main.add(timer, forMode: .common)
    }

    func stop() {
        refreshTimer?.invalidate()
        refreshTimer = nil
    }

    @objc private func refreshTimerFired() {
        refresh()
    }

    func refresh() {
        guard let data = try? Data(contentsOf: stateURL),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return }

        let queue = object["last_queue"] as? [String: Any] ?? [:]
        snapshot = QueueSnapshot(
            appRunning: object["app_running"] as? Bool ?? false,
            queueState: object["queue_state"] as? String ?? "未知",
            queueLength: intValue(queue["queue_length"]),
            queueRank: intValue(queue["queue_rank"]),
            waitingTimeMinutes: doubleValue(queue["waiting_time_min"]),
            logError: object["log_error"] as? String
        )
    }

    private func intValue(_ value: Any?) -> Int? {
        if let value = value as? NSNumber { return value.intValue }
        if let value = value as? String { return Int(value) }
        return nil
    }

    private func doubleValue(_ value: Any?) -> Double? {
        if let value = value as? NSNumber { return value.doubleValue }
        if let value = value as? String { return Double(value) }
        return nil
    }
}

@MainActor
final class QueueMonitorCoreController {
    private var process: Process?

    func start(externalCore: Bool) {
        guard !externalCore else { return }
        guard process == nil,
              let executableURL = Bundle.main.url(forResource: "CloudZZZQueueMonitorCore", withExtension: nil)
        else { return }

        let process = Process()
        process.executableURL = executableURL
        process.arguments = ["--headless"]
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        process.terminationHandler = { [weak self] _ in
            Task { @MainActor in self?.process = nil }
        }

        do {
            try process.run()
            self.process = process
        } catch {
            self.process = nil
        }
    }

    func stop() {
        guard let process else { return }
        if process.isRunning { process.terminate() }
        self.process = nil
    }
}

@MainActor
final class QueueIslandLayoutModel: ObservableObject {
    @Published var isAttachedToTokenLens = false
}

@MainActor
final class QueueIslandPanelController: NSObject {
    private let panelSize = NSSize(width: 238, height: 33.5)
    private let tokenLensIslandSize = NSSize(width: 358, height: 33.5)

    private let store: QueueStatusStore
    private let layoutModel = QueueIslandLayoutModel()
    private let panel: NSPanel
    private var positionTimer: Timer?

    init(store: QueueStatusStore) {
        self.store = store
        panel = NSPanel(
            contentRect: NSRect(origin: .zero, size: panelSize),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        super.init()

        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.level = .statusBar
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.isReleasedWhenClosed = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
        panel.contentView = NSHostingView(rootView: QueueIslandView(store: store, layoutModel: layoutModel))
    }

    func start() {
        refreshPosition()

        let timer = Timer(timeInterval: 1, target: self, selector: #selector(refreshPosition), userInfo: nil, repeats: true)
        positionTimer = timer
        RunLoop.main.add(timer, forMode: .common)
    }

    func stop() {
        positionTimer?.invalidate()
        positionTimer = nil
        panel.orderOut(nil)
    }

    @objc private func refreshPosition() {
        // The monitor core follows the CloudGame process and writes this flag.
        // Keep the island hidden until the game is actually running.
        guard store.snapshot.appRunning else {
            panel.orderOut(nil)
            return
        }

        guard let screen = NSScreen.main ?? NSScreen.screens.first else { return }
        let tokenLensRunning = NSWorkspace.shared.runningApplications.contains(where: isTokenLens)
        layoutModel.isAttachedToTokenLens = tokenLensRunning
        let x: CGFloat

        if tokenLensRunning {
            // TokenLens uses a 358 x 33.5 compact panel centered on the notch.
            // Touch its left edge directly so the two black islands form one seam.
            x = screen.frame.midX - tokenLensIslandSize.width / 2 - panelSize.width
        } else {
            x = screen.frame.midX - panelSize.width / 2
        }

        panel.setFrame(
            NSRect(
                x: x,
                y: screen.frame.maxY - panelSize.height,
                width: panelSize.width,
                height: panelSize.height
            ),
            display: true
        )
        panel.orderFrontRegardless()
    }

    private func isTokenLens(_ application: NSRunningApplication) -> Bool {
        application.bundleIdentifier == "cn.liuli.tokenlens"
            || application.localizedName == "TokenLens"
    }
}

private struct QueueIslandView: View {
    @ObservedObject var store: QueueStatusStore
    @ObservedObject var layoutModel: QueueIslandLayoutModel

    var body: some View {
        ZStack {
            islandShape
                .fill(Color.black)
                .overlay {
                    islandShape.strokeBorder(Color.white.opacity(0.14), lineWidth: 0.7)
                }

            HStack(spacing: 8) {
                Image(systemName: "gamecontroller.fill")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(.white)

                VStack(alignment: .leading, spacing: 0) {
                    Text(queueText)
                        .font(.system(size: 10.5, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)
                        .lineLimit(1)
                    Text(timeText)
                        .font(.system(size: 8, weight: .medium, design: .rounded))
                        .foregroundStyle(.white.opacity(0.52))
                        .lineLimit(1)
                }

                Spacer(minLength: 0)
            }
            .padding(.horizontal, 13)
        }
        .frame(width: 238, height: 33.5)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("云绝区零，\(queueText)，\(timeText)")
    }

    private var islandShape: UnevenRoundedRectangle {
        UnevenRoundedRectangle(
            topLeadingRadius: 0,
            bottomLeadingRadius: 16.75,
            bottomTrailingRadius: layoutModel.isAttachedToTokenLens ? 0 : 16.75,
            topTrailingRadius: 0,
            style: .continuous
        )
    }

    private var queueText: String {
        let snapshot = store.snapshot
        if snapshot.queueState == "排队成功" { return "已进入游戏" }
        if let rank = snapshot.queueRank { return "前方 \(rank) 人" }
        return snapshot.appRunning ? "等待排队" : "未运行"
    }

    private var timeText: String {
        if let minutes = store.snapshot.waitingTimeMinutes {
            return String(format: "预计 %.1f 分钟", minutes)
        }
        if store.snapshot.queueState == "排队成功" { return "排队完成" }
        return store.snapshot.logError ?? "等待数据"
    }
}

@MainActor
final class QueueMonitorAppDelegate: NSObject, NSApplicationDelegate {
    private let store = QueueStatusStore()
    private let coreController = QueueMonitorCoreController()
    private var islandController: QueueIslandPanelController?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        coreController.start(externalCore: CommandLine.arguments.contains("--external-core"))
        store.start()

        let controller = QueueIslandPanelController(store: store)
        islandController = controller
        controller.start()
    }

    func applicationWillTerminate(_ notification: Notification) {
        islandController?.stop()
        store.stop()
        coreController.stop()
    }
}

@main
struct CloudZZZQueueMonitorApp: App {
    @NSApplicationDelegateAdaptor(QueueMonitorAppDelegate.self) private var appDelegate

    var body: some Scene {
        Settings {
            EmptyView()
        }
    }
}
