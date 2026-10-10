import Cocoa

/// 候选窗口。

/// 不用 IMKCandidates：小篆码位（U+3D000 区块 / PUA 补区）在系统字体里没有，
/// 必须用自带的 ShuowenSeal 字体渲染，所以这里全部自绘。
final class CandidateView: NSView {

    var candidates: [SealCandidate] = [] {
        didSet { needsDisplay = true }
    }
    var selectedIndex: Int = 0 {
        didSet { needsDisplay = true }
    }
    /// 提示行：显示当前拼音或无匹配信息
    var hint: String = "" {
        didSet { needsDisplay = true }
    }

    private let cellWidth: CGFloat = 62
    private let cellHeight: CGFloat = 76
    private let padX: CGFloat = 8
    private let padY: CGFloat = 6
    private let hintHeight: CGFloat = 22
    private let maxPerRow: Int = 7

    private var sealFont: NSFont = .systemFont(ofSize: 40)
    private var smallFont: NSFont = .systemFont(ofSize: 11)
    private var hintFont: NSFont = .systemFont(ofSize: 13)

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.backgroundColor = NSColor.windowBackgroundColor.cgColor
        layer?.cornerRadius = 6
    }

    required init?(coder: NSCoder) { fatalError("not supported") }

    /// 注册并选用自带小篆字体。
    func useSealFont(named name: String) {
        if let f = NSFont(name: name, size: 40) {
            sealFont = f
        } else {
            NSLog("[ShuowenIME] 找不到字体 \(name)，候选将显示为占位方块")
        }
    }

    func sizeFor(count: Int, hint: String) -> NSSize {
        self.hint = hint
        let perRow = min(max(count, 1), maxPerRow)
        let rows = max(1, Int(ceil(Double(max(count, 1)) / Double(maxPerRow))))
        return NSSize(
            width: padX * 2 + CGFloat(perRow) * cellWidth,
            height: hintHeight + padY * 2 + CGFloat(rows) * cellHeight
        )
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)

        // 提示行
        let hintRect = NSRect(x: padX, y: bounds.height - hintHeight, width: bounds.width - padX * 2, height: hintHeight)
        (hint as NSString).draw(in: hintRect, withAttributes: [
            .font: hintFont,
            .foregroundColor: NSColor.secondaryLabelColor,
        ])

        guard !candidates.isEmpty else { return }

        let attributes: [NSAttributedString.Key: Any] = [
            .font: sealFont,
            .foregroundColor: NSColor.labelColor,
        ]
        let idxAttributes: [NSAttributedString.Key: Any] = [
            .font: smallFont,
            .foregroundColor: NSColor.tertiaryLabelColor,
        ]

        for (i, cand) in candidates.enumerated() {
            let col = i % maxPerRow
            let row = i / maxPerRow
            let x = padX + CGFloat(col) * cellWidth
            let y = bounds.height - hintHeight - padY - CGFloat(row + 1) * cellHeight

            let cell = NSRect(x: x, y: y, width: cellWidth, height: cellHeight)
            if i == selectedIndex {
                NSColor.selectedContentBackgroundColor.withAlphaComponent(0.25).setFill()
                NSBezierPath(roundedRect: cell.insetBy(dx: 1, dy: 1), xRadius: 4, yRadius: 4).fill()
            }

            // 小篆字形
            let glyphRect = NSRect(x: x, y: y + 16, width: cellWidth, height: cellHeight - 18)
            let para = NSMutableParagraphStyle()
            para.alignment = .center
            var attrs = attributes
            attrs[.paragraphStyle] = para
            (cand.seal as NSString).draw(in: glyphRect, withAttributes: attrs)

            // 对应现代汉字（提示用）
            var sub = idxAttributes
            sub[.paragraphStyle] = para
            var subAttrs = sub
            subAttrs[.foregroundColor] = NSColor.secondaryLabelColor
            (cand.hanzi as NSString).draw(
                in: NSRect(x: x, y: y + 15, width: cellWidth, height: 14),
                withAttributes: subAttrs)

            // 序号
            attrs[.paragraphStyle] = para
            var numAttrs = idxAttributes
            numAttrs[.paragraphStyle] = para
            ("\(i + 1)" as NSString).draw(
                in: NSRect(x: x, y: y + 1, width: cellWidth, height: 13),
                withAttributes: numAttrs)
        }
    }
}

/// 候选面板控制器：管窗口显示/定位。
final class CandidatePanel {
    private var window: NSPanel?
    private var view: CandidateView

    init(sealFontName: String) {
        view = CandidateView(frame: .zero)
        view.useSealFont(named: sealFontName)
    }

    func show(candidates: [SealCandidate], selected: Int, hint: String, at point: NSPoint) {
        view.candidates = candidates
        view.selectedIndex = selected
        let size = view.sizeFor(count: candidates.count, hint: hint)
        if window == nil {
            let w = NSPanel(
                contentRect: NSRect(origin: .zero, size: size),
                styleMask: [.borderless, .nonactivatingPanel],
                backing: .buffered,
                defer: false)
            w.isFloatingPanel = true
            w.level = .popUpMenu
            w.hasShadow = true
            w.backgroundColor = .clear
            w.isOpaque = false
            w.contentView = view
            window = w
        }
        guard let w = window else { return }
        w.setContentSize(size)
        // 定位：光标左下方一点，避免超出屏幕
        var origin = NSPoint(x: point.x, y: point.y - size.height - 6)
        if let screen = NSScreen.main {
            let f = screen.visibleFrame
            origin.x = min(max(origin.x, f.minX + 4), f.maxX - size.width - 4)
            if origin.y < f.minY + 4 { origin.y = point.y + 22 }
        }
        w.setFrameOrigin(origin)
        w.orderFrontRegardless()
    }

    func hide() {
        window?.orderOut(nil)
    }

    var isVisible: Bool { window?.isVisible ?? false }
}
