import Cocoa
import MediaPlayer

@main
struct YtmMediaBridge {
    static let ytmPath = "/Users/justin/.pyenv/shims/ytm"

    static func main() {
        let center = MPRemoteCommandCenter.shared()

        // AirPods in-ear detection dispatches togglePlayPauseCommand for
        // both removal and insertion. Map it to `ytm pause` so removal
        // stops playback and insertion is a no-op (pause is idempotent).
        // Resuming must happen via an explicit play (keyboard / UI).
        center.togglePlayPauseCommand.isEnabled = true
        center.togglePlayPauseCommand.addTarget { _ in
            run("pause")
            return .success
        }

        center.playCommand.isEnabled = true
        center.playCommand.addTarget { _ in
            run("play")
            return .success
        }

        center.pauseCommand.isEnabled = true
        center.pauseCommand.addTarget { _ in
            run("pause")
            return .success
        }

        center.nextTrackCommand.isEnabled = true
        center.nextTrackCommand.addTarget { _ in
            run("next")
            return .success
        }

        center.previousTrackCommand.isEnabled = true
        center.previousTrackCommand.addTarget { _ in
            run("prev")
            return .success
        }

        // Become the "Now Playing" app so macOS routes media events here.
        let info = MPNowPlayingInfoCenter.default()
        info.nowPlayingInfo = [
            MPMediaItemPropertyTitle: "ytm-player",
            MPNowPlayingInfoPropertyPlaybackRate: 1.0,
        ]
        info.playbackState = .playing

        NSLog("ytm-media-bridge: listening for media key events")
        RunLoop.current.run()
    }

    static func run(_ command: String) {
        NSLog("ytm-media-bridge: running ytm %@", command)
        let task = Process()
        task.executableURL = URL(fileURLWithPath: ytmPath)
        task.arguments = [command]
        // Pass through PATH so pyenv shim can find the real Python.
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/Users/justin/.pyenv/shims:/usr/local/bin:/usr/bin:/bin"
        env["PYENV_ROOT"] = "/Users/justin/.pyenv"
        task.environment = env
        do {
            try task.run()
        } catch {
            NSLog("ytm-media-bridge: failed to run ytm %@: %@", command, error.localizedDescription)
        }
    }
}
