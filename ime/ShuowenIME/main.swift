import Cocoa
import InputMethodKit

// 输入法服务入口。
//
// InputMethodKit 的约定：
//   * connectionName 必须与 Info.plist 的 InputMethodConnectionName 一致；
//   * delegate 类需在 Info.plist 的 InputMethodServerControllerClass 里声明。

let kConnectionName = "ShuowenIME_Connection"
let kServerControllerClass = "SealInputController"

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

        server = IMKServer(name: kConnectionName, bundleIdentifier: Bundle.main.bundleIdentifier)
        if server == nil {
            NSLog("[ShuowenIME] IMKServer 启动失败")
        }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
