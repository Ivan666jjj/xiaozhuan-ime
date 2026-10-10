import Cocoa
import CoreText

/// 偏好设置窗口。
///
/// 为什么自己弹窗口、不用 IMK 自带的 `showPreferences:` + nib：
/// vChewing 实测后者在 macOS 12 上不可靠（提交记录里写着
/// "Stop using IMK's showPreferences: This turns out to be unreliable on macOS 12"），
/// 社区最终都改成自研窗口。而且本项目用 swiftc 直接编译、没有 Xcode 工程，
/// 本来也没有 nib 可用。
///
/// 预览区直接复用 `CandidateView`，所以看到的就是真实候选窗效果。
final class PrefWindowController: NSWindowController {

    static let shared = PrefWindowController()

    private let sizeSlider = NSSlider(value: Double(Pref.sizeDefault),
                                      minValue: Double(Pref.sizeRange.lowerBound),
                                      maxValue: Double(Pref.sizeRange.upperBound),
                                      target: nil, action: nil)
    private let sizeValue = NSTextField(labelWithString: "")
    private let perRowControl = NSSegmentedControl(labels: ["5", "6", "7", "8", "10", "12"],
                                                   trackingMode: .selectOne,
                                                   target: nil, action: nil)
    private let hanziCheck = NSButton(checkboxWithTitle: "候选下方显示对应汉字（方便对认）",
                                      target: nil, action: nil)
    private let preview = CandidateView(frame: .zero)
    private let previewBox = NSBox()

    /// 候选窗用的篆体名（与 SealInputController 保持一致）。
    static let sealFontName = "Shuowen Seal"

    /// 字体没装到系统时，从 bundle 注册一份（进程级），好让预览显示篆形。
    /// 字体没找到就退化成系统字体 —— 预览仍可用，只是看到的是普通汉字。
    private func ensureSealFontAvailable() {
        guard NSFont(name: Self.sealFontName, size: 12) == nil else { return }
        if let url = Bundle.main.url(forResource: "ShuowenSeal", withExtension: "ttf") {
            var err: Unmanaged<CFError>?
            CTFontManagerRegisterFontsForURL(url as CFURL, .process, &err)
        }
    }

    private init() {
        let win = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 620, height: 460),
            styleMask: [.titled, .closable],
            backing: .buffered,
            defer: false)
        win.title = "小篆输入法 · 偏好设置"
        win.isReleasedWhenClosed = false
        win.center()
        super.init(window: win)
        buildUI()
        syncFromPref()
    }

    required init?(coder: NSCoder) { fatalError("not supported") }

    // ---------------------------------------------------------------- UI

    private func buildUI() {
        guard let content = window?.contentView else { return }

        sizeSlider.target = self
        sizeSlider.action = #selector(sizeChanged)
        sizeSlider.isContinuous = true
        sizeSlider.widthAnchor.constraint(equalToConstant: 320).isActive = true

        sizeValue.font = .monospacedDigitSystemFont(ofSize: 13, weight: .medium)
        sizeValue.alignment = .right
        sizeValue.widthAnchor.constraint(equalToConstant: 64).isActive = true

        perRowControl.target = self
        perRowControl.action = #selector(perRowChanged)

        hanziCheck.target = self
        hanziCheck.action = #selector(hanziToggled)

        previewBox.title = "预览"
        previewBox.titlePosition = .atTop
        previewBox.boxType = .primary
        previewBox.translatesAutoresizingMaskIntoConstraints = false
        previewBox.contentView?.addSubview(preview)
        preview.translatesAutoresizingMaskIntoConstraints = false
        if let cv = previewBox.contentView {
            NSLayoutConstraint.activate([
                preview.leadingAnchor.constraint(equalTo: cv.leadingAnchor, constant: 8),
                preview.trailingAnchor.constraint(equalTo: cv.trailingAnchor, constant: -8),
                preview.topAnchor.constraint(equalTo: cv.topAnchor, constant: 8),
                preview.bottomAnchor.constraint(equalTo: cv.bottomAnchor, constant: -8),
            ])
        }

        let restore = NSButton(title: "恢复默认", target: self, action: #selector(restoreDefaults))
        restore.bezelStyle = .rounded
        let done = NSButton(title: "完成", target: self, action: #selector(closeWindow))
        done.bezelStyle = .rounded
        done.keyEquivalent = "\r"

        let rowSize = NSStackView(views: [label("候选字号"), sizeSlider, sizeValue])
        rowSize.spacing = 10
        rowSize.alignment = .centerY

        let rowPer = NSStackView(views: [label("每行候选"), perRowControl])
        rowPer.spacing = 10
        rowPer.alignment = .centerY

        let buttons = NSStackView(views: [restore, done])
        buttons.spacing = 8
        buttons.orientation = .horizontal

        let root = NSStackView(views: [rowSize, rowPer, hanziCheck, previewBox, buttons])
        root.orientation = .vertical
        root.alignment = .leading
        root.spacing = 14
        root.edgeInsets = NSEdgeInsets(top: 20, left: 22, bottom: 18, right: 22)
        root.translatesAutoresizingMaskIntoConstraints = false

        content.addSubview(root)
        NSLayoutConstraint.activate([
            root.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            root.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            root.topAnchor.constraint(equalTo: content.topAnchor),
            root.bottomAnchor.constraint(equalTo: content.bottomAnchor),
            previewBox.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 22),
            previewBox.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -22),
            previewBox.heightAnchor.constraint(equalToConstant: 170),
            previewBox.widthAnchor.constraint(equalTo: root.widthAnchor, constant: -44),
        ])
        buttons.trailingAnchor.constraint(
            equalTo: root.trailingAnchor, constant: -22).isActive = true

        refreshPreview()
    }

    private func label(_ s: String) -> NSTextField {
        let t = NSTextField(labelWithString: s)
        t.alignment = .right
        t.widthAnchor.constraint(equalToConstant: 72).isActive = true
        return t
    }

    /// 预览用的样例候选（“shui” 的真实候选那样排）。
    private func refreshPreview() {
        ensureSealFontAvailable()
        preview.useSealFont(named: Self.sealFontName)   // 不设的话预览是普通汉字，跟真实候选窗不符
        preview.hint = "shui"
        preview.selectedIndex = 0
        preview.candidates = ["水", "说", "税", "睡", "谁", "酒"].map { h in
            SealCandidate(hanzi: h, seal: h)
        }
        preview.needsDisplay = true
    }

    private func syncFromPref() {
        let p = Pref.shared
        sizeSlider.doubleValue = Double(p.candidateSize)
        sizeValue.stringValue = "\(Int(p.candidateSize)) pt"
        hanziCheck.state = p.showHanzi ? .on : .off
        let opts = [5, 6, 7, 8, 10, 12]
        perRowControl.selectedSegment = opts.firstIndex(of: p.perRow) ?? 2
        preview.needsLayout = true
        refreshPreview()
    }

    // ------------------------------------------------------------ actions

    @objc private func sizeChanged() {
        // 取整，避免滑出 40.0000001 这种值
        let v = sizeSlider.doubleValue.rounded()
        sizeSlider.doubleValue = v
        sizeValue.stringValue = "\(Int(v)) pt"
        Pref.shared.candidateSize = CGFloat(v)
        refreshPreview()
    }

    @objc private func perRowChanged() {
        let opts = [5, 6, 7, 8, 10, 12]
        let i = perRowControl.selectedSegment
        guard i >= 0, i < opts.count else { return }
        Pref.shared.perRow = opts[i]
        refreshPreview()
    }

    @objc private func hanziToggled() {
        Pref.shared.showHanzi = hanziCheck.state == .on
        refreshPreview()
    }

    @objc private func restoreDefaults() {
        Pref.shared.resetToDefaults()
        syncFromPref()
    }

    @objc private func closeWindow() {
        window?.close()
    }

    // -------------------------------------------------------------- show

    /// 显示窗口（输入法菜单调用）。输入法是后台进程，必须显式激活才看得见。
    func show() {
        syncFromPref()
        window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
}
