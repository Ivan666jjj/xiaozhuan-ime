import Cocoa

/// 用户偏好。
///
/// 单独成一层，界面与候选窗共享同一份数据 —— 参考 vChewing 的 `PrefMgr` /
/// `UserDef` 与 msime 的做法：值一律存 `UserDefaults`（自己的 bundle domain），
/// 改动后发通知，候选窗立即重绘，不用重启输入法。
///
/// 取值范围都做 clamp（vChewing 对候选字号 clamp 在 12...196）。候选窗是自绘的，
/// 字号过小时下方的序号/汉字提示会挤成一团，过大时窗口会超出屏幕，所以两头都收着点。
enum PrefKey {
    static let candidateSize = "candidateSize"
    static let perRow = "candidatePerRow"
    static let showHanzi = "showCandidateHanzi"
}

final class Pref {
    static let shared = Pref()
    /// 任何偏好变化都会发这个通知，候选窗监听它重绘。
    static let didChange = Notification.Name("ShuowenPrefDidChange")

    static let sizeRange: ClosedRange<CGFloat> = 20...120
    static let sizeDefault: CGFloat = 40
    static let perRowRange: ClosedRange<Int> = 3...12
    static let perRowDefault: Int = 7

    private let d = UserDefaults.standard

    private init() {}

    /// 候选字号（pt）。
    var candidateSize: CGFloat {
        get {
            let raw = d.object(forKey: PrefKey.candidateSize) as? Double
            let v = CGFloat(raw ?? Double(Pref.sizeDefault))
            return min(max(v, Pref.sizeRange.lowerBound), Pref.sizeRange.upperBound)
        }
        set {
            let v = min(max(newValue, Pref.sizeRange.lowerBound), Pref.sizeRange.upperBound)
            d.set(Double(v), forKey: PrefKey.candidateSize)
            post()
        }
    }

    /// 每行放几个候选。
    var perRow: Int {
        get {
            guard let raw = d.object(forKey: PrefKey.perRow) as? Int else {
                return Pref.perRowDefault
            }
            return min(max(raw, Pref.perRowRange.lowerBound), Pref.perRowRange.upperBound)
        }
        set {
            let v = min(max(newValue, Pref.perRowRange.lowerBound), Pref.perRowRange.upperBound)
            d.set(v, forKey: PrefKey.perRow)
            post()
        }
    }

    /// 候选下方是否显示对应的现代汉字（方便对认）。
    var showHanzi: Bool {
        get { d.object(forKey: PrefKey.showHanzi) as? Bool ?? true }
        set {
            d.set(newValue, forKey: PrefKey.showHanzi)
            post()
        }
    }

    func resetToDefaults() {
        d.removeObject(forKey: PrefKey.candidateSize)
        d.removeObject(forKey: PrefKey.perRow)
        d.removeObject(forKey: PrefKey.showHanzi)
        post()
    }

    private func post() {
        NotificationCenter.default.post(name: Pref.didChange, object: nil)
    }
}
