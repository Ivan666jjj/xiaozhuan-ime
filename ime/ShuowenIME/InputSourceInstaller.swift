import Carbon
import Foundation

/// 把本输入法注册/启用/选中到系统。
///
/// 为什么需要这个：把 .app 拷进 `~/Library/Input Methods/` 只是「已安装」，
/// 系统并不会自动「注册」它——必须调用 `TISRegisterInputSource`，
/// 之后它才会出现在「系统设置 → 键盘 → 输入法」的可用列表里。
/// 只靠拷贝 + 重启服务是不行的（实测反复注销重登也无效）。
///
/// 用法：
///     ShuowenIME --register-input-source
///     ShuowenIME --enable-input-source
///     ShuowenIME --select-input-source
enum InputSourceInstaller {

    /// 与 Info.plist 的 CFBundleIdentifier 保持一致
    static let bundleID = "com.local.inputmethod.ShuowenSeal"

    /// 输入模式 ID 的后缀部分（完整 ID = bundleID + suffix）
    static let inputModeSuffix = ".Seal"

    /// 注册输入源。这是让系统「认识」本输入法的关键一步。
    @discardableResult
    static func register() -> OSStatus {
        TISRegisterInputSource(Bundle.main.bundleURL as CFURL)
    }

    /// 加入已启用列表。
    @discardableResult
    static func enable() -> OSStatus {
        guard let source = inputSource() else { return OSStatus(fnfErr) }
        return TISEnableInputSource(source)
    }

    /// 切换为当前输入法。
    @discardableResult
    static func select() -> OSStatus {
        guard let source = inputSource() else { return OSStatus(fnfErr) }
        return TISSelectInputSource(source)
    }

    /// 找到本输入法的输入模式。
    static func inputSource() -> TISInputSource? {
        guard let raw = TISCreateInputSourceList(nil, true)?.takeRetainedValue() else {
            return nil
        }
        for index in 0..<CFArrayGetCount(raw) {
            let source = unsafeBitCast(CFArrayGetValueAtIndex(raw, index), to: TISInputSource.self)
            guard
                let idRef = TISGetInputSourceProperty(source, kTISPropertyInputSourceID),
                let bundleRef = TISGetInputSourceProperty(source, kTISPropertyBundleID)
            else { continue }
            let sourceID = unsafeBitCast(idRef, to: CFString.self) as String
            let sourceBundleID = unsafeBitCast(bundleRef, to: CFString.self) as String
            if sourceBundleID == bundleID, sourceID.hasSuffix(inputModeSuffix) {
                return source
            }
        }
        return nil
    }

    /// 打印当前状态（供 --status 使用）。
    static func describe() -> String {
        let source = inputSource()
        let list = TISCreateInputSourceList(nil, true)?.takeRetainedValue()
        let total = list.map { CFArrayGetCount($0) } ?? 0
        var lines = ["输入源总数: \(total)"]
        if let s = source {
            let id = (TISGetInputSourceProperty(s, kTISPropertyInputSourceID)
                      .map { unsafeBitCast($0, to: CFString.self) as String }) ?? "?"
            let enabled = TISGetInputSourceProperty(s, kTISPropertyInputSourceIsEnabled) != nil
            lines.append("找到输入模式: \(id)")
            lines.append("已启用标记: \(enabled)")
        } else {
            lines.append("✘ 未找到输入模式（未注册？）")
        }
        return lines.joined(separator: "\n")
    }
}
