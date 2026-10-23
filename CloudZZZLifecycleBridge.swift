import AppKit
import Foundation

@MainActor
final class CloudZZZLifecycleBridge: NSObject {
    private let workspace = NSWorkspace.shared
    private let cloudGameBundleIdentifier = "com.miHoYo.cloudgames.Nap"
    private let monitorBundleIdentifier = "com.liuli.cloud-zzz-queue-monitor"
    private let queueStateMaximumAge: TimeInterval = 180
    private var synchronizationTimer: Timer?
    private var queueSleepActivity: NSObjectProtocol?

    private var queueStateURL: URL {
        if let overridePath = ProcessInfo.processInfo.environment["CLOUD_ZZZ_STATE_FILE"],
           !overridePath.isEmpty {
            return URL(fileURLWithPath: overridePath)
        }

        return FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/CloudZZZQueueMonitor/state/status.json")
    }

    func start() {
        let center = workspace.notificationCenter
        center.addObserver(
            self,
            selector: #selector(applicationStateChanged(_:)),
            name: NSWorkspace.didLaunchApplicationNotification,
            object: nil
        )
        center.addObserver(
            self,
            selector: #selector(applicationStateChanged(_:)),
            name: NSWorkspace.didTerminateApplicationNotification,
            object: nil
        )

        let timer = Timer(
            timeInterval: 1,
            target: self,
            selector: #selector(periodicSynchronization(_:)),
            userInfo: nil,
            repeats: true
        )
        synchronizationTimer = timer
        RunLoop.main.add(timer, forMode: .common)
        synchronize()
    }

    @objc private func applicationStateChanged(_ notification: Notification) {
        synchronize()
    }

    @objc private func periodicSynchronization(_ timer: Timer) {
        synchronize()
    }

    private func synchronize() {
        let cloudGameIsRunning = workspace.runningApplications.contains(where: isCloudGame)
        let monitorApplications = workspace.runningApplications.filter {
            $0.bundleIdentifier == monitorBundleIdentifier
        }

        synchronizeQueueSleepProtection(cloudGameIsRunning: cloudGameIsRunning)

        if cloudGameIsRunning {
            if monitorApplications.isEmpty {
                launchMonitor()
            }
        } else {
            monitorApplications.forEach { $0.terminate() }
        }
    }

    private func synchronizeQueueSleepProtection(cloudGameIsRunning: Bool) {
        let shouldProtect = cloudGameIsRunning && queueStateIsFreshAndQueueing()

        if shouldProtect, queueSleepActivity == nil {
            queueSleepActivity = ProcessInfo.processInfo.beginActivity(
                options: [.idleSystemSleepDisabled],
                reason: "云·绝区零正在排队，保持网络和 VPN 连接"
            )
            log("Queueing detected: system idle sleep disabled; display sleep remains enabled.")
        } else if !shouldProtect, let activity = queueSleepActivity {
            ProcessInfo.processInfo.endActivity(activity)
            queueSleepActivity = nil
            log("Queueing ended or became stale: normal system sleep restored.")
        }
    }

    private func queueStateIsFreshAndQueueing(now: Date = Date()) -> Bool {
        guard let data = try? Data(contentsOf: queueStateURL),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              object["queue_state"] as? String == "排队中",
              let updatedAt = object["updated_at"] as? NSNumber else {
            return false
        }

        let age = now.timeIntervalSince1970 - updatedAt.doubleValue
        return age >= -30 && age <= queueStateMaximumAge
    }

    private func log(_ message: String) {
        let formatter = ISO8601DateFormatter()
        print("[\(formatter.string(from: Date()))] \(message)")
        fflush(stdout)
    }

    private func isCloudGame(_ application: NSRunningApplication) -> Bool {
        if application.bundleIdentifier == cloudGameBundleIdentifier {
            return true
        }

        if application.localizedName == "云·绝区零" {
            return true
        }

        let executablePath = application.executableURL?.standardizedFileURL.path ?? ""
        return executablePath.contains("/CloudGame.app/Contents/MacOS/CloudGame")
    }

    private func launchMonitor() {
        let executableURL = URL(fileURLWithPath: CommandLine.arguments[0]).standardizedFileURL
        let appURL = executableURL
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()

        guard FileManager.default.fileExists(atPath: appURL.path) else { return }

        let configuration = NSWorkspace.OpenConfiguration()
        configuration.activates = false
        configuration.addsToRecentItems = false
        workspace.openApplication(at: appURL, configuration: configuration) { _, _ in }
    }
}

@main
struct CloudZZZLifecycleBridgeMain {
    @MainActor
    static func main() {
        let bridge = CloudZZZLifecycleBridge()
        bridge.start()
        RunLoop.main.run()
    }
}
