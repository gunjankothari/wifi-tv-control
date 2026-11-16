#!/usr/bin/env swift
// Draws the TV Remote app icon and writes icon/TVRemote.icns (Mac), icon/TVRemote.ico (Windows)
// and icon/TVRemote.png (1024 px preview). Run from the project folder:  swift icon/make-icon.swift
// The outputs are committed, so this only needs re-running when the drawing below changes.
import AppKit

// MARK: - Helpers

struct P { var x: CGFloat; var y: CGFloat }

func col(_ hex: UInt32, _ a: CGFloat = 1) -> CGColor {
    CGColor(srgbRed: CGFloat((hex >> 16) & 255) / 255, green: CGFloat((hex >> 8) & 255) / 255,
            blue: CGFloat(hex & 255) / 255, alpha: a)
}

func gradient(_ colors: [CGColor], _ locations: [CGFloat]? = nil) -> CGGradient {
    CGGradient(colorsSpace: CGColorSpace(name: CGColorSpace.sRGB)!, colors: colors as CFArray, locations: locations)!
}

/// Rounded rectangle with Apple-style continuous ("squircle") corners, built the way Figma's corner
/// smoothing does it. Coordinates are y-down. smoothing 0.6 matches the macOS icon mask.
func squircle(_ rect: CGRect, radius: CGFloat, smoothing: CGFloat = 0.6) -> CGPath {
    let r = min(radius, min(rect.width, rect.height) / 2)
    let p = min((1 + smoothing) * r, min(rect.width, rect.height) / 2)
    let arcDeg = 90 * (1 - smoothing)
    let arcLen = sin(arcDeg / 2 * .pi / 180) * r * sqrt(2)
    let alpha = (90 - arcDeg) / 2
    let p3p4 = r * tan(alpha / 2 * .pi / 180)
    let beta = 45 * smoothing
    let c = p3p4 * cos(beta * .pi / 180)
    let d = c * tan(beta * .pi / 180)
    let b = (p - arcLen - c - d) / 3
    let a = 2 * b
    let k = 4 / 3 * tan(arcDeg * .pi / 180 / 4)      // cubic approximation of the circular part

    // corner point, direction we arrive along, direction we leave along (all y-down)
    let corners: [(P, P, P)] = [
        (P(x: rect.maxX, y: rect.minY), P(x: 1, y: 0), P(x: 0, y: 1)),    // top right
        (P(x: rect.maxX, y: rect.maxY), P(x: 0, y: 1), P(x: -1, y: 0)),   // bottom right
        (P(x: rect.minX, y: rect.maxY), P(x: -1, y: 0), P(x: 0, y: -1)),  // bottom left
        (P(x: rect.minX, y: rect.minY), P(x: 0, y: -1), P(x: 1, y: 0)),   // top left
    ]
    let path = CGMutablePath()
    for (i, (corner, inDir, outDir)) in corners.enumerated() {
        func g(_ lx: CGFloat, _ ly: CGFloat) -> CGPoint {
            CGPoint(x: corner.x + lx * inDir.x + ly * outDir.x, y: corner.y + lx * inDir.y + ly * outDir.y)
        }
        let start = g(-p, 0)
        if i == 0 { path.move(to: start) } else { path.addLine(to: start) }
        // straight-ish lead in
        let s = (x: -p + a + b + c, y: d)                       // where the circular part starts
        let e = (x: -d, y: p - a - b - c)                       // where it ends
        path.addCurve(to: g(s.x, s.y), control1: g(-p + a, 0), control2: g(-p + a + b, 0))
        // circular part, centre at (-r, r)
        let us = ((s.x + r) / r, (s.y - r) / r), ue = ((e.x + r) / r, (e.y - r) / r)
        let ts = (-us.1, us.0), te = (-ue.1, ue.0)              // travel directions (clockwise, y-down)
        path.addCurve(to: g(e.x, e.y),
                      control1: g(s.x + k * r * ts.0, s.y + k * r * ts.1),
                      control2: g(e.x - k * r * te.0, e.y - k * r * te.1))
        // lead out
        path.addCurve(to: g(0, p), control1: g(e.x + d, e.y + c), control2: g(e.x + d, e.y + b + c))
    }
    path.closeSubpath()
    return path
}

// MARK: - The drawing (1024 x 1024, y-down)

func drawIcon(_ ctx: CGContext, size: CGFloat) {
    let s = size / 1024
    ctx.translateBy(x: 0, y: size)
    ctx.scaleBy(x: s, y: -s)
    ctx.setAllowsAntialiasing(true)
    ctx.interpolationQuality = .high

    // Background plate (Apple's grid: 824 pt square centred in 1024)
    let plate = squircle(CGRect(x: 100, y: 100, width: 824, height: 824), radius: 185)
    ctx.saveGState()
    ctx.setShadow(offset: CGSize(width: 0, height: -10 * s), blur: 26 * s, color: col(0x000000, 0.32))
    ctx.addPath(plate); ctx.setFillColor(col(0x1A2150)); ctx.fillPath()
    ctx.restoreGState()

    ctx.saveGState()
    ctx.addPath(plate); ctx.clip()
    ctx.drawLinearGradient(gradient([col(0x3650C8), col(0x1B2466), col(0x10143A)], [0, 0.6, 1]),
                           start: CGPoint(x: 512, y: 100), end: CGPoint(x: 512, y: 924), options: [])
    // glow coming off the screen
    let glowC = CGPoint(x: 500, y: 470)
    ctx.drawRadialGradient(gradient([col(0x3FE3D4, 0.55), col(0x3FE3D4, 0.18), col(0x3FE3D4, 0)], [0, 0.45, 1]),
                           startCenter: glowC, startRadius: 0, endCenter: glowC, endRadius: 470, options: [])
    ctx.restoreGState()

    // TV bezel
    let bezelRect = CGRect(x: 212, y: 268, width: 576, height: 392)
    let bezel = squircle(bezelRect, radius: 52)
    ctx.saveGState()
    ctx.setShadow(offset: CGSize(width: 0, height: -16 * s), blur: 34 * s, color: col(0x000000, 0.40))
    ctx.addPath(bezel); ctx.setFillColor(col(0xF2F4FA)); ctx.fillPath()
    ctx.restoreGState()
    ctx.saveGState()
    ctx.addPath(bezel); ctx.clip()
    ctx.drawLinearGradient(gradient([col(0xFFFFFF), col(0xE3E7F1)]),
                           start: CGPoint(x: 512, y: bezelRect.minY), end: CGPoint(x: 512, y: bezelRect.maxY), options: [])
    ctx.restoreGState()

    // Screen
    let screenRect = bezelRect.insetBy(dx: 26, dy: 26)
    let screen = squircle(screenRect, radius: 32)
    ctx.saveGState()
    ctx.addPath(screen); ctx.clip()
    ctx.drawLinearGradient(gradient([col(0x4FE9D8), col(0x2BB8E8), col(0x3A6CFF)], [0, 0.5, 1]),
                           start: CGPoint(x: screenRect.minX, y: screenRect.minY),
                           end: CGPoint(x: screenRect.maxX, y: screenRect.maxY), options: [])
    // sheen across the top of the glass
    let sheen = CGMutablePath()
    sheen.move(to: CGPoint(x: screenRect.minX, y: screenRect.minY))
    sheen.addLine(to: CGPoint(x: screenRect.maxX, y: screenRect.minY))
    sheen.addLine(to: CGPoint(x: screenRect.maxX, y: screenRect.minY + 110))
    sheen.addQuadCurve(to: CGPoint(x: screenRect.minX, y: screenRect.minY + 190),
                       control: CGPoint(x: screenRect.midX, y: screenRect.minY + 230))
    sheen.closeSubpath()
    ctx.addPath(sheen); ctx.clip()
    ctx.drawLinearGradient(gradient([col(0xFFFFFF, 0.34), col(0xFFFFFF, 0.06)]),
                           start: CGPoint(x: 512, y: screenRect.minY), end: CGPoint(x: 512, y: screenRect.minY + 230), options: [])
    ctx.restoreGState()
    // inner edge of the bezel
    ctx.saveGState()
    ctx.addPath(screen); ctx.setStrokeColor(col(0x000000, 0.10)); ctx.setLineWidth(3); ctx.strokePath()
    ctx.restoreGState()

    // Stand
    ctx.saveGState()
    ctx.setShadow(offset: CGSize(width: 0, height: -8 * s), blur: 18 * s, color: col(0x000000, 0.35))
    ctx.setFillColor(col(0xE6EAF3))
    ctx.addPath(CGPath(roundedRect: CGRect(x: 472, y: 656, width: 80, height: 44), cornerWidth: 10, cornerHeight: 10, transform: nil))
    ctx.fillPath()
    ctx.addPath(CGPath(roundedRect: CGRect(x: 352, y: 690, width: 320, height: 34), cornerWidth: 17, cornerHeight: 17, transform: nil))
    ctx.setFillColor(col(0xF2F4FA)); ctx.fillPath()
    ctx.restoreGState()

    // Remote, leaning against the bottom right
    ctx.saveGState()
    ctx.translateBy(x: 724, y: 668)
    ctx.rotate(by: 22 * .pi / 180)
    let body = CGRect(x: -74, y: -196, width: 148, height: 392)
    let bodyPath = squircle(body, radius: 60)
    ctx.saveGState()
    ctx.setShadow(offset: CGSize(width: 6 * s, height: -18 * s), blur: 30 * s, color: col(0x000000, 0.50))
    ctx.addPath(bodyPath); ctx.setFillColor(col(0x262B38)); ctx.fillPath()
    ctx.restoreGState()
    ctx.saveGState()
    ctx.addPath(bodyPath); ctx.clip()
    ctx.drawLinearGradient(gradient([col(0x3C4353), col(0x20242E)]),
                           start: CGPoint(x: body.minX, y: body.minY), end: CGPoint(x: body.maxX, y: body.maxY), options: [])
    ctx.restoreGState()
    ctx.addPath(bodyPath); ctx.setStrokeColor(col(0xFFFFFF, 0.14)); ctx.setLineWidth(3); ctx.strokePath()

    // power button
    ctx.setFillColor(col(0xFF5A5A))
    ctx.fillEllipse(in: CGRect(x: -20, y: -170, width: 40, height: 40))
    ctx.setStrokeColor(col(0xFFFFFF)); ctx.setLineWidth(5); ctx.setLineCap(.round)
    ctx.addArc(center: CGPoint(x: 0, y: -150), radius: 11, startAngle: -.pi / 2 + 0.6, endAngle: -.pi / 2 - 0.6, clockwise: false)
    ctx.strokePath()
    ctx.move(to: CGPoint(x: 0, y: -162)); ctx.addLine(to: CGPoint(x: 0, y: -150)); ctx.strokePath()
    // D-pad ring with centre button
    ctx.setStrokeColor(col(0x5E6678)); ctx.setLineWidth(26)
    ctx.strokeEllipse(in: CGRect(x: -45, y: -95, width: 90, height: 90))
    ctx.setFillColor(col(0x8E96A8))
    ctx.fillEllipse(in: CGRect(x: -18, y: -68, width: 36, height: 36))
    // volume / channel rockers
    ctx.setFillColor(col(0x4A5162))
    for x in [-50, 18] as [CGFloat] {
        ctx.addPath(CGPath(roundedRect: CGRect(x: x, y: 32, width: 32, height: 96), cornerWidth: 16, cornerHeight: 16, transform: nil))
        ctx.fillPath()
    }
    ctx.setFillColor(col(0x8E96A8))
    for (x, y) in [(-34, 52), (34, 52), (-34, 108), (34, 108)] as [(CGFloat, CGFloat)] {
        ctx.fillEllipse(in: CGRect(x: x - 5, y: y - 5, width: 10, height: 10))
    }
    // a couple of small keys near the bottom
    ctx.setFillColor(col(0x4A5162))
    for x in [-40, -6, 28] as [CGFloat] {
        ctx.fillEllipse(in: CGRect(x: x, y: 148, width: 16, height: 16))
    }
    ctx.restoreGState()
}

// MARK: - Output

func render(_ px: Int) -> (Data, NSBitmapImageRep) {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: px, pixelsHigh: px, bitsPerSample: 8,
                               samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                               colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    let ctx = NSGraphicsContext(bitmapImageRep: rep)!.cgContext
    drawIcon(ctx, size: CGFloat(px))
    return (rep.representation(using: .png, properties: [:])!, rep)
}

let root = URL(fileURLWithPath: CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "icon")
let fm = FileManager.default
let iconset = root.appendingPathComponent("TVRemote.iconset")
try? fm.removeItem(at: iconset)
try fm.createDirectory(at: iconset, withIntermediateDirectories: true)

var pngs: [Int: Data] = [:]
for px in [16, 32, 48, 64, 128, 256, 512, 1024] { pngs[px] = render(px).0 }

for pt in [16, 32, 128, 256, 512] {
    try pngs[pt]!.write(to: iconset.appendingPathComponent("icon_\(pt)x\(pt).png"))
    try pngs[pt * 2]!.write(to: iconset.appendingPathComponent("icon_\(pt)x\(pt)@2x.png"))
}
try pngs[1024]!.write(to: root.appendingPathComponent("TVRemote.png"))

let task = Process()
task.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
task.arguments = ["-c", "icns", iconset.path, "-o", root.appendingPathComponent("TVRemote.icns").path]
try task.run(); task.waitUntilExit()
guard task.terminationStatus == 0 else { print("iconutil failed"); exit(1) }
try? fm.removeItem(at: iconset)

// Windows .ico: a directory of PNG-compressed images (supported since Vista)
let icoSizes = [16, 32, 48, 256]
var ico = Data()
func u16(_ v: Int) { ico.append(UInt8(v & 255)); ico.append(UInt8((v >> 8) & 255)) }
func u32(_ v: Int) { u16(v & 0xFFFF); u16((v >> 16) & 0xFFFF) }
u16(0); u16(1); u16(icoSizes.count)
var offset = 6 + 16 * icoSizes.count
for px in icoSizes {
    let d = pngs[px]!
    ico.append(UInt8(px == 256 ? 0 : px)); ico.append(UInt8(px == 256 ? 0 : px))
    ico.append(0); ico.append(0); u16(1); u16(32); u32(d.count); u32(offset)
    offset += d.count
}
for px in icoSizes { ico.append(pngs[px]!) }
try ico.write(to: root.appendingPathComponent("TVRemote.ico"))
print("Wrote TVRemote.icns, TVRemote.ico and TVRemote.png to \(root.path)")
