import Cocoa
import InputMethodKit

// 输入法服务入口。
//
// InputMethodKit 的约定：
//   * connectionName 必须与 Info.plist 的 InputMethodConnectionName 一致；
//   * 控制器类名需在 Info.plist 的 InputMethodServerControllerClass 里声明。
//
// 另外提供几条 CLI 子命令用于「注册 / 启用 / 选中」本输入法。
// 只把 .app 拷进 ~/Library/Input Methods/ 是不够的——系统不会自动注册它，
// 必须调用 TISRegisterInputSource，否则它不会出现在系统设置的输入法列表里
// （实测：仅拷贝 + 重启服务 + 反复注销重登，都不会让它出现）。

// ⚠️ macOS 26+ 起，imklaunchagent 只接受 `$(CFBundleIdentifier)_Connection` 形式的
// 连接名；别的形式会被拒（日志里报 "Refusing connection name for bundle:
// unrecognized 'InputMethodConnectionName' value"），表现为输入法已注册、
// 能枚举、TISSelectInputSource 却返回 paramErr(-50)、切换键里永远轮不到它。
// 先写成与 Info.plist 一致的常量；下方启动时还会用 Bundle.main 再校一次。
let kConnectionName = "com.local.inputmethod.ShuowenSeal_Connection"

@objc(AppDelegate)
final class AppDelegate: NSObject, NSApplicationDelegate {
    var server: IMKServer?

    func applicationDidFinishLaunching(_ notification: Notification) {
        // 载入词典（与可执行文件同目录的 Resources 里）
        if let url = Bundle.main.url(forResource: "seal_dict", withExtension: "json") {
            SealDictionary.shared.load(from: url)
        } else {
            NSLog("[ShuowenIME] 找不到 seal_dict.json")
        }
        SealInputController.ensureFontRegistered()

        server = IMKServer(name: kConnectionName,
                           bundleIdentifier: Bundle.main.bundleIdentifier)
        if server == nil {
            NSLog("[ShuowenIME] IMKServer 启动失败")
        }
    }
}

// ---- CLI 子命令：安装器调用这几个动作 ----

func runInstallerAction(_ action: String) -> Never {
    let status: OSStatus
    switch action {
    case "--register-input-source":
        status = InputSourceInstaller.register()
    case "--enable-input-source":
        status = InputSourceInstaller.enable()
    case "--select-input-source":
        status = InputSourceInstaller.select()
    default:
        status = OSStatus(paramErr)
    }
    if status == noErr {
        print("小焕的小篆输入法：\(action) 成功")
        exit(EXIT_SUCCESS)
    } else {
        FileHandle.standardError.write(
            "小焕的小篆输入法：\(action) 失败（OSStatus \(status)）\n".data(using: .utf8)!)
        exit(EXIT_FAILURE)
    }
}

if let first = CommandLine.arguments.dropFirst().first,
   first.hasPrefix("--"), first.hasSuffix("-input-source") {
    if first == "--status-input-source" {
        print(InputSourceInstaller.describe())
        exit(EXIT_SUCCESS)
    }
    runInstallerAction(first)
}

// 单独打开偏好设置窗口（也可以从输入法菜单进）。
// 刚装完、还没注销重登、切不到输入法时，用它最省事：
//   "…/小焕的小篆输入法.app/Contents/MacOS/ShuowenIME" --prefs
if CommandLine.arguments.dropFirst().first == "--prefs" {
    let app = NSApplication.shared
    app.setActivationPolicy(.accessory)   // 不出现在 Dock
    PrefWindowController.shared.show()
    app.run()
    exit(EXIT_SUCCESS)
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
