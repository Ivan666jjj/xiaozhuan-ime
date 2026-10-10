import Foundation

/// 一个拼音候选。
struct SealCandidate {
    let hanzi: String   // 现代汉字
    let seal: String    // 小篆字符（U+3D000 区块或 PUA 补区）
    /// 是否来自补区（PUA）——补区字符离开自带字体不可移植。
    var isPua: Bool {
        guard let v = seal.unicodeScalars.first?.value else { return false }
        return v >= 0xF0000 && v <= 0xF0000 + (0x9FFF - 0x3400)
    }
}

/// 拼音 -> 候选 的词典，从 seal_dict.json 载入。
final class SealDictionary {
    static let shared = SealDictionary()

    private var dict: [String: [SealCandidate]] = [:]
    private(set) var pinyinCount = 0
    private(set) var loaded = false

    private init() {}

    func load(from url: URL) {
        guard !loaded else { return }
        do {
            let data = try Data(contentsOf: url)
            guard let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let raw = obj["dict"] as? [String: [[String]]] else {
                NSLog("[ShuowenIME] 词典结构异常: \(url.path)")
                return
            }
            var parsed: [String: [SealCandidate]] = [:]
            parsed.reserveCapacity(raw.count)
            for (py, rows) in raw {
                var list: [SealCandidate] = []
                list.reserveCapacity(rows.count)
                for row in rows where row.count >= 2 {
                    list.append(SealCandidate(hanzi: row[0], seal: row[1]))
                }
                if !list.isEmpty { parsed[py] = list }
            }
            dict = parsed
            pinyinCount = parsed.count
            loaded = true
            NSLog("[ShuowenIME] 词典载入完成：\(parsed.count) 个拼音")
        } catch {
            NSLog("[ShuowenIME] 词典载入失败: \(error)")
        }
    }

    /// 查询候选；`limit` 限制返回数量。
    func candidates(for pinyin: String, limit: Int = 30) -> [SealCandidate] {
        guard let list = dict[pinyin.lowercased()] else { return [] }
        return Array(list.prefix(limit))
    }

    func has(pinyin: String) -> Bool {
        dict[pinyin.lowercased()] != nil
    }

    /// 前缀匹配：用于输入未完成时的预览（如输入 "sh" 时提示）。
    func prefixes(of pinyin: String, limit: Int = 20) -> [String] {
        let key = pinyin.lowercased()
        guard key.count >= 1 else { return [] }
        var out: [String] = []
        for py in dict.keys where py.hasPrefix(key) {
            out.append(py)
            if out.count >= limit { break }
        }
        return out.sorted()
    }
}
