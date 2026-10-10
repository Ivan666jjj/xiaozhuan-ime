import Cocoa
import InputMethodKit

/// 小篆输入法的输入控制器。
///
/// 交互：输入无声调拼音（如 `shui`）→ 候选窗显示对应的小篆字形 →
/// 数字键 / 空格选字，回车提交拼音原文，Esc 清空。
///
/// 注意 `@objc(SealInputController)`：Info.plist 的
/// `InputMethodServerControllerClass` 由 ObjC runtime 按名字实例化，
/// Swift 类若没有 ObjC 名，系统会解析不出输入模式（表现为
/// `TISTypeKeyboardInputMethodWithoutModes`）。
@objc(SealInputController)
final class SealInputController: IMKInputController {

    private var buffer: String = ""
    private var candidates: [SealCandidate] = []
    private var selected = 0
    private var panel: CandidatePanel?
    /// 最近一次使用的输入客户端：字号/布局改了要按新尺寸重排候选窗，得记住它。
    private var lastClient: IMKTextInput?

    private let maxCandidates = 28

    override init!(server: IMKServer!, delegate: Any!, client inputClient: Any!) {
        super.init(server: server, delegate: delegate, client: inputClient)
        if let name = SealInputController.sealFontName {
            panel = CandidatePanel(sealFontName: name)
        } else {
            panel = CandidatePanel(sealFontName: "Shuowen Seal")
        }
        SealInputController.ensureFontRegistered()
    }

    // MARK: - 字体

    private static var fontRegistered = false
    private static let fontFamily = "Shuowen Seal"

    /// 从 bundle 里注册自带字体（进程级）。真正要让其它 app 显示小篆，
    /// 还需要把字体装到 ~/Library/Fonts（见 Makefile 的 install-font）。
    static func ensureFontRegistered() {
        guard !fontRegistered else { return }
        fontRegistered = true
        guard let url = Bundle.main.url(forResource: "ShuowenSeal", withExtension: "ttf") else {
            NSLog("[ShuowenIME] bundle 里找不到 ShuowenSeal.ttf")
            return
        }
        var err: Unmanaged<CFError>?
        let ok = CTFontManagerRegisterFontsForURL(url as CFURL, .process, &err)
        if !ok {
            NSLog("[ShuowenIME] 字体注册失败: \(String(describing: err))")
        }
    }

    /// 检查字体是否可用；不可用时返回 nil。
    static var sealFontName: String? {
        NSFontManager.shared.availableFontFamilies.contains(fontFamily) ? fontFamily : nil
    }

    // MARK: - 按键处理

    override func handle(_ event: NSEvent!, client sender: Any!) -> Bool {
        guard let event = event, event.type == .keyDown else { return false }
        guard let client = sender as? IMKTextInput else { return false }

        let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        // 带 Command/Control 的按键交给系统
        if flags.contains(.command) || flags.contains(.control) { return false }

        let chars = event.charactersIgnoringModifiers ?? ""

        // Esc：清空
        if event.keyCode == 53 {
            if buffer.isEmpty { return false }
            reset(client: client)
            return true
        }

        // 回车：提交拼音原文
        if event.keyCode == 36 || event.keyCode == 76 {
            if buffer.isEmpty { return false }
            commit(text: buffer, client: client)
            return true
        }

        // 退格
        if event.keyCode == 51 {
            if buffer.isEmpty { return false }
            buffer.removeLast()
            refresh(client: client)
            return true
        }

        // 空格：选第一个候选
        if chars == " " {
            if buffer.isEmpty { return false }
            commitSelected(client: client)
            return true
        }

        // 数字 1-9：选第 N 个候选
        if let n = Int(chars), n >= 1, n <= 9, !buffer.isEmpty {
            if n <= candidates.count {
                selected = n - 1
                commitSelected(client: client)
                return true
            }
            return false
        }

        // 翻页：- / =
        if !buffer.isEmpty, chars == "-" || chars == "=" {
            let step = candidates.count > 0 ? min(9, candidates.count) : 9
            selected = chars == "="
                ? min(selected + step, max(candidates.count - 1, 0))
                : max(selected - step, 0)
            refresh(client: client)
            return true
        }

        // 字母：累积拼音
        let lowered = chars.lowercased()
        guard lowered.count == 1, let ch = lowered.first, ch.isLetter, ch.isASCII else {
            return false
        }
        // 'v' 代表 ü
        buffer.append(ch)
        refresh(client: client)
        return true
    }

    // MARK: - 状态与候选

    private func reset(client: IMKTextInput) {
        buffer = ""
        candidates = []
        selected = 0
        panel?.hide()
        // 清掉 marked text
        client.setMarkedText(
            "", selectionRange: NSRange(location: 0, length: 0), replacementRange: NSRange(location: NSNotFound, length: 0))
    }

    private func refresh(client: IMKTextInput) {
        // marked text 显示当前拼音，方便用户看到输入状态
        let marked = buffer
        client.setMarkedText(
            marked,
            selectionRange: NSRange(location: marked.utf16.count, length: 0),
            replacementRange: NSRange(location: NSNotFound, length: 0))

        candidates = SealDictionary.shared.candidates(for: buffer, limit: maxCandidates)
        selected = 0

        guard !candidates.isEmpty else {
            let hint = buffer.isEmpty ? "" : "「\(buffer)」没有对应的篆字"
            showPanel(client: client, hint: hint)
            return
        }
        showPanel(client: client, hint: "\(buffer)  —  数字/空格选字，回车提交拼音")
    }

    private func showPanel(client: IMKTextInput, hint: String) {
        guard let panel = panel else { return }
        lastClient = client          // 字号变了要按新尺寸重排，得记住当前的 client
        // 取当前光标的行高矩形，用来定位候选窗
        var lineRect = NSRect.zero
        client.attributes(forCharacterIndex: 0, lineHeightRectangle: &lineRect)
        panel.show(candidates: candidates, selected: selected, hint: hint, at: lineRect.origin)
    }

    private func commitSelected(client: IMKTextInput) {
        guard selected < candidates.count else {
            commit(text: buffer, client: client)
            return
        }
        let cand = candidates[selected]
        // 上屏**现代汉字**（BMP）：在编辑器里把文字字体设为 Shuowen Seal 即显示篆形。
        // 不用 U+3D000 小篆码位 —— 那是超 BMP，分享到没装字体的机器上就是豆腐块。
        commit(text: cand.hanzi, client: client)
    }

    private func commit(text: String, client: IMKTextInput) {
        client.insertText(text, replacementRange: NSRange(location: NSNotFound, length: 0))
        reset(client: client)
    }

    override func deactivateServer(_ sender: Any!) {
        if let client = sender as? IMKTextInput {
            reset(client: client)
        }
        super.deactivateServer(sender)
    }

    override func commitComposition(_ sender: Any!) {
        if let client = sender as? IMKTextInput, !buffer.isEmpty {
            commit(text: buffer, client: client)
        }
        super.commitComposition(sender)
    }

    // ------------------------------------------------------------ 输入法菜单

    /// 输入法菜单（点菜单栏的输入法图标时出现）。
    ///
    /// 不用 IMK 自带的 `showPreferences(_:)`：它默认去找 `preferences.nib`，
    /// 而本项目没有 nib（swiftc 直接编译），且该机制在新版 macOS 上被证实不可靠
    /// （见 PreferencesWindow.swift 的注释）。所以菜单项自己挂、窗口自己弹。
    override func menu() -> NSMenu! {
        let menu = NSMenu(title: "小篆输入法")

        let prefs = NSMenuItem(title: "偏好设置…",
                               action: #selector(openPreferences(_:)), keyEquivalent: "")
        prefs.target = self
        menu.addItem(prefs)

        menu.addItem(.separator())

        let bigger = NSMenuItem(title: "放大候选字",
                                action: #selector(makeFontBigger(_:)), keyEquivalent: "")
        bigger.target = self
        menu.addItem(bigger)

        let smaller = NSMenuItem(title: "缩小候选字",
                                 action: #selector(makeFontSmaller(_:)), keyEquivalent: "")
        smaller.target = self
        menu.addItem(smaller)

        let reset = NSMenuItem(title: "恢复默认字号（\(Int(Pref.sizeDefault)) pt）",
                               action: #selector(resetFontSize(_:)), keyEquivalent: "")
        reset.target = self
        menu.addItem(reset)

        return menu
    }

    @objc private func openPreferences(_ sender: Any?) {
        PrefWindowController.shared.show()
    }

    @objc private func makeFontBigger(_ sender: Any?) {
        Pref.shared.candidateSize += 6
        reformatOpenPanel()
    }

    @objc private func makeFontSmaller(_ sender: Any?) {
        Pref.shared.candidateSize -= 6
        reformatOpenPanel()
    }

    @objc private func resetFontSize(_ sender: Any?) {
        Pref.shared.candidateSize = Pref.sizeDefault
        reformatOpenPanel()
    }

    /// 字号变了，让正开着的候选窗按新尺寸重排（没开就不用管，下次显示自然是新的）。
    private func reformatOpenPanel() {
        guard let client = lastClient, !candidates.isEmpty else { return }
        showPanel(client: client, hint: "\(buffer)  —  数字/空格选字，回车提交拼音")
    }
}
