// 查询系统输入法注册状态（TIS = Text Input Source）。
//
// 用途：确认「小焕的小篆输入法」是否已被 macOS 识别，以及它是不是
// “键盘类输入法”（只有这一类才会出现在 系统设置 → 键盘 → 输入法 里）。
//
//   swiftc -O -o /tmp/tis_check tools/tis_check.swift && /tmp/tis_check
//
// 输出示例：
//   ✔ com.local.inputmethod.ShuowenSeal | 小焕的小篆输入法 | TISTypeKeyboardInputMethodModeEnabled

import Carbon
import Foundation

func prop(_ src: TISInputSource, _ key: CFString) -> Any? {
    guard let p = TISGetInputSourceProperty(src, key) else { return nil }
    return Unmanaged<AnyObject>.fromOpaque(p).takeUnretainedValue()
}

func boolProp(_ src: TISInputSource, _ key: CFString) -> Bool? {
    guard let p = TISGetInputSourceProperty(src, key) else { return nil }
    return CFBooleanGetValue(Unmanaged<CFBoolean>.fromOpaque(p).takeUnretainedValue())
}

let keyword = CommandLine.arguments.count > 1 ? CommandLine.arguments[1].lowercased() : "shuowen"

guard let all = TISCreateInputSourceList(nil, true)?.takeRetainedValue() as? [TISInputSource] else {
    print("无法枚举输入源")
    exit(1)
}
let enabled = (TISCreateInputSourceList(nil, false)?.takeRetainedValue() as? [TISInputSource]) ?? []

print("全部输入源: \(all.count)   已启用: \(enabled.count)")

var matched = 0
for src in all {
    let id = (prop(src, kTISPropertyInputSourceID) as? String) ?? ""
    guard id.lowercased().contains(keyword) else { continue }
    matched += 1
    let name = (prop(src, kTISPropertyLocalizedName) as? String) ?? "?"
    let type = (prop(src, kTISPropertyInputSourceType) as? String) ?? "?"
    let isOn = boolProp(src, kTISPropertyInputSourceIsEnabled) ?? false
    let canPick = boolProp(src, kTISPropertyInputSourceIsSelectCapable) ?? false
    print("✔ \(id) | \(name) | \(type)")
    print("    已启用: \(isOn)  可选中: \(canPick)")
}

if matched == 0 {
    print("✘ 没有匹配「\(keyword)」的输入源 —— 系统未识别该输入法")
    exit(2)
}

// 是否为键盘类输入法（决定它会不会出现在系统设置的输入法列表里）
let keyboardTypes = ["TISTypeKeyboardInputMethod", "TISTypeKeyboardInputMode",
                     "TISTypeKeyboardInputMethodModeEnabled",
                     "TISTypeKeyboardInputMethodWithoutModes"]
var isKeyboard = false
for src in all {
    let id = (prop(src, kTISPropertyInputSourceID) as? String) ?? ""
    guard id.lowercased().contains(keyword) else { continue }
    let t = (prop(src, kTISPropertyInputSourceType) as? String) ?? ""
    if keyboardTypes.contains(where: { t.hasPrefix($0) }) { isKeyboard = true }
}
print(isKeyboard ? "✔ 属于键盘类输入法（会出现在系统设置里）"
                 : "✘ 不是键盘类输入法 —— 系统设置里看不到它，多半是 Info.plist 的输入模式声明有问题")
exit(isKeyboard ? 0 : 3)
