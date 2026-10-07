import AppKit
import RunSpecimenCore

/// Keeps the SwiftUI `Window` on a real display, resizable, and Full Screen capable.
enum WindowSanitizer {
    private static var observers: [NSObjectProtocol] = []
    private static var launchDeadline = Date.distantPast
    private static var fullscreenTransitionWindows = Set<ObjectIdentifier>()

    static func shouldSkipFrameSanitize(isFullScreen: Bool, isTransitioningToOrFromFullScreen: Bool) -> Bool {
        isFullScreen || isTransitioningToOrFromFullScreen
    }

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
        observeFullScreenTransitions(center)
        apply()
        DispatchQueue.main.async { apply() }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { apply() }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { apply() }
    }

    private static func observeFullScreenTransitions(_ center: NotificationCenter) {
        observers.append(center.addObserver(forName: NSWindow.willEnterFullScreenNotification, object: nil, queue: .main) { note in
            guard let window = note.object as? NSWindow else { return }
            beginFullScreenTransition(window)
            enableFullScreen(window)
        })
        observers.append(center.addObserver(forName: NSWindow.willExitFullScreenNotification, object: nil, queue: .main) { note in
            guard let window = note.object as? NSWindow else { return }
            beginFullScreenTransition(window)
        })
        observers.append(center.addObserver(forName: NSWindow.didEnterFullScreenNotification, object: nil, queue: .main) { note in
            guard let window = note.object as? NSWindow else { return }
            endFullScreenTransition(window)
            enableFullScreen(window)
        })
        observers.append(center.addObserver(forName: NSWindow.didExitFullScreenNotification, object: nil, queue: .main) { note in
            guard let window = note.object as? NSWindow else { return }
            endFullScreenTransition(window)
            apply(window)
        })
    }

    private static func beginFullScreenTransition(_ window: NSWindow) {
        let id = ObjectIdentifier(window)
        fullscreenTransitionWindows.insert(id)
        // AppKit has no did-fail-to-enter/exit notification. Drop the flag if
        // didEnter/didExit never arrives so a failed transition cannot stick.
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            fullscreenTransitionWindows.remove(id)
        }
    }

    private static func endFullScreenTransition(_ window: NSWindow) {
        fullscreenTransitionWindows.remove(ObjectIdentifier(window))
    }

    static func apply() {
        NSApp.windows.forEach(apply)
    }

    static func apply(_ window: NSWindow) {
        guard isMainWindow(window) else { return }
        enableFullScreen(window)
        if shouldSkipFrameSanitize(
            isFullScreen: window.styleMask.contains(.fullScreen),
            isTransitioningToOrFromFullScreen: fullscreenTransitionWindows.contains(ObjectIdentifier(window))
        ) {
            return
        }

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

    static func isMainWindow(_ window: NSWindow) -> Bool {
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
