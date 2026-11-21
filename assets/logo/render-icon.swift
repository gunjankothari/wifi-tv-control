// Renders app-icon.svg geometry to a 1024x1024 PNG (CoreGraphics, no dependencies).
// Usage: swift assets/logo/render-icon.swift assets/logo/app-icon-1024.png
import AppKit

let out = CommandLine.arguments[1]
let S = 1024
let cs = CGColorSpace(name: CGColorSpace.sRGB)!
let ctx = CGContext(data: nil, width: S, height: S, bitsPerComponent: 8, bytesPerRow: 0, space: cs,
                    bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
ctx.translateBy(x: 0, y: CGFloat(S)); ctx.scaleBy(x: 1, y: -1) // SVG coordinates
let c1 = CGColor(srgbRed: 0x5b / 255.0, green: 0x8c / 255.0, blue: 1, alpha: 1)
let c2 = CGColor(srgbRed: 0xa4 / 255.0, green: 0x6b / 255.0, blue: 1, alpha: 1)
let grad = CGGradient(colorsSpace: cs, colors: [c1, c2] as CFArray, locations: [0, 1])!
ctx.drawLinearGradient(grad, start: .zero, end: CGPoint(x: 1024, y: 1024), options: [])
ctx.setStrokeColor(CGColor(gray: 1, alpha: 1)); ctx.setFillColor(CGColor(gray: 1, alpha: 1))
ctx.setLineWidth(48); ctx.setLineCap(.round)
ctx.addPath(CGPath(roundedRect: CGRect(x: 192, y: 252, width: 640, height: 400),
                   cornerWidth: 72, cornerHeight: 72, transform: nil))
ctx.strokePath()
ctx.move(to: CGPoint(x: 392, y: 752)); ctx.addLine(to: CGPoint(x: 632, y: 752)); ctx.strokePath()
ctx.setLineWidth(30); ctx.setLineJoin(.round)
for pts in [[(480, 366), (512, 334), (544, 366)], [(480, 538), (512, 570), (544, 538)],
            [(426, 420), (394, 452), (426, 484)], [(598, 420), (630, 452), (598, 484)]] {
    ctx.move(to: CGPoint(x: pts[0].0, y: pts[0].1))
    for p in pts.dropFirst() { ctx.addLine(to: CGPoint(x: p.0, y: p.1)) }
    ctx.strokePath()
}
ctx.fillEllipse(in: CGRect(x: 482, y: 422, width: 60, height: 60))
let rep = NSBitmapImageRep(cgImage: ctx.makeImage()!)
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: out))
