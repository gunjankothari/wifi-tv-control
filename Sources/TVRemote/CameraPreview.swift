import AVFoundation
import SwiftUI

/// Plays the same live stream the TV receives, so the preview matches what is on screen
/// (including its few seconds of delay). Muted by default to avoid echo with the TV speakers.
struct CameraPreview: NSViewRepresentable {
    var muted: Bool

    static let streamURL = URL(string: "http://127.0.0.1:8767/cam/stream.m3u8")!

    final class PlayerView: NSView {
        let player = AVPlayer(url: CameraPreview.streamURL)
        override init(frame: NSRect) {
            super.init(frame: frame)
            wantsLayer = true
            let layer = AVPlayerLayer(player: player)
            layer.videoGravity = .resizeAspectFill
            layer.backgroundColor = NSColor.black.cgColor
            self.layer = layer
            player.isMuted = true
            player.play()
        }
        required init?(coder: NSCoder) { fatalError() }
        deinit { player.pause() }
    }

    func makeNSView(context: Context) -> PlayerView { PlayerView(frame: .zero) }

    func updateNSView(_ view: PlayerView, context: Context) {
        view.player.isMuted = muted
        if view.player.timeControlStatus == .paused { view.player.play() }
    }
}
