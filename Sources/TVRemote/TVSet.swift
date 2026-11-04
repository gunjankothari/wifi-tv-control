import SwiftUI

/// A television seen at an angle, with `content` shown on its screen. The set leans a little towards the mouse.
struct TVSet<Content: View>: View {
    @ViewBuilder var content: Content

    private static var resting: CGSize { CGSize(width: -12, height: 5) }   // degrees around the vertical and horizontal axes
    @State private var tilt = TVSet.resting

    private var metal: LinearGradient {
        LinearGradient(colors: [Color(white: 0.34), Color(white: 0.10)], startPoint: .top, endPoint: .bottom)
    }

    var body: some View {
        GeometryReader { geo in
            VStack(spacing: 0) {
                ZStack {
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(LinearGradient(colors: [Color(white: 0.30), Color(white: 0.07)],
                                             startPoint: .topLeading, endPoint: .bottomTrailing))
                    content
                        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                        .padding(7)
                    // glass sheen across the screen
                    RoundedRectangle(cornerRadius: 6, style: .continuous)
                        .fill(LinearGradient(colors: [.white.opacity(0.16), .clear],
                                             startPoint: .topLeading, endPoint: UnitPoint(x: 0.55, y: 0.5)))
                        .padding(7)
                        .allowsHitTesting(false)
                }
                .aspectRatio(16.0 / 9.0, contentMode: .fit)
                .shadow(color: .black.opacity(0.35), radius: 12, x: 8, y: 12)
                RoundedRectangle(cornerRadius: 2).fill(metal).frame(width: 34, height: 10)
                Capsule().fill(metal).frame(width: 118, height: 7)
            }
            .padding(.horizontal, 10)
            .rotation3DEffect(.degrees(tilt.width), axis: (x: 0, y: 1, z: 0), perspective: 0.5)
            .rotation3DEffect(.degrees(tilt.height), axis: (x: 1, y: 0, z: 0), perspective: 0.5)
            .animation(.interactiveSpring(response: 0.3, dampingFraction: 0.8), value: tilt)
            .onContinuousHover { phase in
                switch phase {
                case .active(let p):
                    let nx = p.x / max(geo.size.width, 1) - 0.5
                    let ny = p.y / max(geo.size.height, 1) - 0.5
                    tilt = CGSize(width: TVSet.resting.width + nx * 18, height: TVSet.resting.height - ny * 12)
                case .ended:
                    tilt = TVSet.resting
                }
            }
        }
        .frame(height: 192)
    }
}
