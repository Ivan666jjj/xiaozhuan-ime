// 常用字体检表 v2：缺篆形的格子自动标红
import Cocoa
import CoreText

let sealDesc = (CTFontManagerCreateFontDescriptorsFromURL(
    URL(fileURLWithPath: "/Users/Admin/Library/Fonts/ShuowenSeal.ttf") as CFURL) as! [CTFontDescriptor])[0]
func sealF(_ s: CGFloat) -> CTFont { CTFontCreateWithFontDescriptor(sealDesc, s, nil) }
func kaiF(_ s: CGFloat) -> CTFont { CTFontCreateWithName("Kaiti SC" as CFString, s, nil) }

// 字体实际覆盖的码位
let cmapFont = CTFontCreateWithFontDescriptor(sealDesc, 100, nil)
let charset = CTFontCopyCharacterSet(cmapFont) as! CharacterSet

let cols = 10, rows = 10, cell: CGFloat = 150
let W = CGFloat(cols) * cell + 80, H = CGFloat(rows) * cell + 220
let ctx = CGContext(data: nil, width: Int(W), height: Int(H), bitsPerComponent: 8, bytesPerRow: 0,
                    space: CGColorSpaceCreateDeviceRGB(),
                    bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
ctx.setFillColor(CGColor(red: 0.984, green: 0.976, blue: 0.961, alpha: 1))
ctx.fill(CGRect(x: 0, y: 0, width: W, height: H))

func draw(_ t: String, _ f: CTFont, cx: CGFloat, cy: CGFloat, gray: CGFloat) {
    let a: [CFString: Any] = [kCTFontAttributeName: f,
        kCTForegroundColorAttributeName: CGColor(red: gray, green: gray, blue: gray, alpha: 1)]
    let ln = CTLineCreateWithAttributedString(CFAttributedStringCreate(nil, t as CFString, a as CFDictionary)!)
    let b = CTLineGetBoundsWithOptions(ln, .useOpticalBounds)
    ctx.textPosition = CGPoint(x: cx - b.width/2 - b.origin.x, y: cy)
    CTLineDraw(ln, ctx)
}

let chars = Array("的一是了我不人在他有这个上们来到时大地为子中你说生国年着就那和要她出也得里后自以会家可下而过天去能对小多然于心学么之都好看起发当没成只如事把还用第样道想作种开美总从无情己面最女但现前些所同日手又行意动方期它头经长儿回位分爱老因很给名法间斯知世什两次使身者被高已亲其进此话常与活正感")

var missing: [String] = []
for i in 0..<min(chars.count, cols*rows) {
    let ch = chars[i], r = i / cols, c = i % cols
    let cx = 40 + CGFloat(c) * cell + cell/2
    let cy = H - 140 - CGFloat(r + 1) * cell
    // 检测这个字在不在字体里
    let has = ch.unicodeScalars.allSatisfy { charset.contains($0) }
    if !has {
        missing.append(String(ch))
        // 标红底
        ctx.setFillColor(CGColor(red: 0.99, green: 0.90, blue: 0.90, alpha: 1))
        ctx.fill(CGRect(x: cx - 62, y: cy - 34, width: 124, height: 110))
        ctx.setStrokeColor(CGColor(red: 0.85, green: 0.55, blue: 0.55, alpha: 1))
        ctx.setLineWidth(1.5)
        ctx.stroke(CGRect(x: cx - 62, y: cy - 34, width: 124, height: 110))
    }
    draw(String(ch), sealF(104), cx: cx, cy: cy + 28, gray: has ? 0.10 : 0.55)
    draw(String(ch), kaiF(24), cx: cx, cy: cy - 22, gray: 0.52)
}

draw("常用字体检表（现代汉语最高频 100 字）", kaiF(28), cx: W/2, cy: H - 70, gray: 0.30)
let n = min(chars.count, cols*rows)
draw("有篆形 \(n - missing.count)/\(n)　｜　红框 = 无篆形，显示的是楷体：\(missing.joined(separator: " "))",
     kaiF(22), cx: W/2, cy: 60, gray: 0.45)
draw("—— 小焕的小篆输入法", kaiF(18), cx: W/2, cy: 30, gray: 0.58)

let out = "/Users/Admin/Desktop/常用字体检表.png"
let d = CGImageDestinationCreateWithURL(URL(fileURLWithPath: out) as CFURL, "public.png" as CFString, 1, nil)!
CGImageDestinationAddImage(d, ctx.makeImage()!, nil)
CGImageDestinationFinalize(d)
print("  ✓ 体检表 v2：有篆形 \(n - missing.count)/\(n)，缺 \(missing.count) 个：\(missing.joined(separator: " "))")
