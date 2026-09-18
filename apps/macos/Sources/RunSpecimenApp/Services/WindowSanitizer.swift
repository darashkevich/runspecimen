import AppKit
import RunSpecimenCore

/// Keeps the SwiftUI `WindowGroup` on a real display, resizable, and Full Screen capable.
enum WindowSanitizer {
    private static var observers: [NSObjectProtocol] = []
    private static var launchDeadline = Date.distantPast

    static func install() {
        guard observers.isEmpty else {
            apply()
            return
        }
        launchDeadline = Date().addingTimeInterval(2.5)
        let center = NotificationCenter.default
        observers.append(center.addObserver(forName: NSWindow.didBecomeKeyNotification, object: nil, queue: .main) { note in
            guard let window = note.object as? NSWindow else { return }
            apply(window)
        })
        observers.append(center.addObserver(forName: NSWindow.didMoveNotification, object: nil, queue: .main) { note in
            guard let window = note.object as? NSWindow else { return }
            if Date() < launchDeadline || needsSanitize(window) {
                apply(window)
            } else {
                enableFullScreen(window)
            }
        })
        observers.append(center.addObserver(forName: NSWindow.didResizeNotification, object: nil, queue: .main) { note in
            guard let window = note.object as? NSWindow else { return }
            if Date() < launchDeadline || needsSanitize(window) {
                apply(window)
            } else {
                enableFullScreen(window)
            }
        })
        apply()
        DispatchQueue.main.async { apply() }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { apply() }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { apply() }
    }

    static func apply() {
        NSApp.windows.forEach(apply)
    }

    static func apply(_ window: NSWindow) {
        guard isMainWindow(window) else { return }
        if window.styleMask.contains(.fullScreen) { return }

        enableFullScreen(window)

        let screens = NSScreen.screens.map(\.visibleFrame)
        let frame = window.frame
        guard WindowPlacement.needsSanitize(frame: frame, screens: screens) else { return }

        let next = WindowPlacement.sanitize(frame: frame, screens: screens)
        window.setFrame(next, display: true, animate: false)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private static func needsSanitize(_ window: NSWindow) -> Bool {
        WindowPlacement.needsSanitize(
            frame: window.frame,
            screens: NSScreen.screens.map(\.visibleFrame)
        )
    }

    private static func enableFullScreen(_ window: NSWindow) {
        window.styleMask.insert([.titled, .closable, .miniaturizable, .resizable])
        window.collectionBehavior.remove([.fullScreenNone, .fullScreenAuxiliary])
        window.collectionBehavior.insert([.fullScreenPrimary, .fullScreenAllowsTiling, .managed])
        window.isRestorable = false
    }

    private static func isMainWindow(_ window: NSWindow) -> Bool {
        if window.isSheet { return false }
        if window.level != .normal { return false }
        if !window.styleMask.contains(.titled) { return false }
        let title = window.title
        if title == "Settings" || title == "Preferences" { return false }
        // CLI / system alerts are small and non-resizable.
        if window.frame.width < 400, !window.styleMask.contains(.resizable) {
            return false
        }
        return title.isEmpty || title == "RunSpecimen"
    }
}
