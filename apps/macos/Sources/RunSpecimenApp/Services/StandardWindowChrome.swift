import AppKit
import Combine

/// Native AppKit window chrome that SwiftUI's single `Window` scene does not
/// always install: View → Enter/Exit Full Screen (⌃⌘F), Esc to leave Full
/// Screen, and the usual Window/File/app menu actions when they are missing.
enum StandardWindowChrome {
    static let escapeKeyCode: UInt16 = 53

    private static var observers: [NSObjectProtocol] = []
    private static var escapeMonitor: Any?
    private static var mainMenuObservation: NSKeyValueObservation?
    private static var isInstallingMenus = false

    static func install() {
        FullScreenSession.shared.start()
        installEscapeMonitor()
        observeMainMenu()
        install(into: NSApp.mainMenu)
        DispatchQueue.main.async { install(into: NSApp.mainMenu) }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { install(into: NSApp.mainMenu) }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { install(into: NSApp.mainMenu) }
    }

    /// Idempotent: fills gaps, never duplicates an equivalent item.
    static func install(into mainMenu: NSMenu?) {
        guard let mainMenu else { return }
        guard !isInstallingMenus else { return }
        isInstallingMenus = true
        defer { isInstallingMenus = false }
        dedupeFullScreenItems(in: mainMenu)
        for need in missingItems(in: mainMenu) {
            add(need, to: mainMenu)
        }
    }

    static func shouldExitFullScreenOnEscape(
        keyCode: UInt16,
        modifierFlags: NSEvent.ModifierFlags,
        isFullScreen: Bool,
        hasSheet: Bool,
        hasModalWindow: Bool,
        hasPopupMenu: Bool
    ) -> Bool {
        guard keyCode == escapeKeyCode, isFullScreen else { return false }
        guard !hasSheet, !hasModalWindow, !hasPopupMenu else { return false }
        let mods = modifierFlags
            .intersection(.deviceIndependentFlagsMask)
            .subtracting([.capsLock, .numericPad, .function])
        return mods.isEmpty
    }

    struct MenuItemNeed: Equatable {
        var title: String
        var action: Selector
        var keyEquivalent: String
        var keyEquivalentModifierMask: NSEvent.ModifierFlags
        var menuTitle: String
    }

    static let requiredItems: [MenuItemNeed] = [
        MenuItemNeed(
            title: "Enter Full Screen",
            action: #selector(NSWindow.toggleFullScreen(_:)),
            keyEquivalent: "f",
            keyEquivalentModifierMask: [.control, .command],
            menuTitle: "View"
        ),
        MenuItemNeed(
            title: "Minimize",
            action: #selector(NSWindow.performMiniaturize(_:)),
            keyEquivalent: "m",
            keyEquivalentModifierMask: [.command],
            menuTitle: "Window"
        ),
        MenuItemNeed(
            title: "Zoom",
            action: #selector(NSWindow.performZoom(_:)),
            keyEquivalent: "",
            keyEquivalentModifierMask: [],
            menuTitle: "Window"
        ),
        MenuItemNeed(
            title: "Bring All to Front",
            action: #selector(NSApplication.arrangeInFront(_:)),
            keyEquivalent: "",
            keyEquivalentModifierMask: [],
            menuTitle: "Window"
        ),
        MenuItemNeed(
            title: "Close",
            action: #selector(NSWindow.performClose(_:)),
            keyEquivalent: "w",
            keyEquivalentModifierMask: [.command],
            menuTitle: "File"
        ),
        MenuItemNeed(
            title: "Hide RunSpecimen",
            action: #selector(NSApplication.hide(_:)),
            keyEquivalent: "h",
            keyEquivalentModifierMask: [.command],
            menuTitle: "RunSpecimen"
        ),
        MenuItemNeed(
            title: "Hide Others",
            action: #selector(NSApplication.hideOtherApplications(_:)),
            keyEquivalent: "h",
            keyEquivalentModifierMask: [.command, .option],
            menuTitle: "RunSpecimen"
        ),
        MenuItemNeed(
            title: "Show All",
            action: #selector(NSApplication.unhideAllApplications(_:)),
            keyEquivalent: "",
            keyEquivalentModifierMask: [],
            menuTitle: "RunSpecimen"
        ),
        MenuItemNeed(
            title: "Quit RunSpecimen",
            action: #selector(NSApplication.terminate(_:)),
            keyEquivalent: "q",
            keyEquivalentModifierMask: [.command],
            menuTitle: "RunSpecimen"
        ),
    ]

    static func missingItems(in mainMenu: NSMenu) -> [MenuItemNeed] {
        requiredItems.filter { !containsEquivalent($0, in: mainMenu) }
    }

    static func containsEquivalent(_ need: MenuItemNeed, in menu: NSMenu) -> Bool {
        contains(in: menu) { item in
            if let action = item.action, action == need.action {
                return true
            }
            if !need.keyEquivalent.isEmpty,
               item.keyEquivalent.lowercased() == need.keyEquivalent.lowercased(),
               sameModifiers(item.keyEquivalentModifierMask, need.keyEquivalentModifierMask) {
                return true
            }
            if item.title == need.title {
                return true
            }
            if need.action == #selector(NSWindow.toggleFullScreen(_:)),
               item.title.localizedCaseInsensitiveContains("Full Screen") {
                return true
            }
            if need.action == #selector(NSWindow.performClose(_:)),
               item.title == "Close Window" {
                return true
            }
            return false
        }
    }

    static func sameModifiers(_ lhs: NSEvent.ModifierFlags, _ rhs: NSEvent.ModifierFlags) -> Bool {
        lhs.intersection(.deviceIndependentFlagsMask) == rhs.intersection(.deviceIndependentFlagsMask)
    }

    private static func contains(in menu: NSMenu, where predicate: (NSMenuItem) -> Bool) -> Bool {
        for item in menu.items {
            if predicate(item) { return true }
            if let submenu = item.submenu, contains(in: submenu, where: predicate) {
                return true
            }
        }
        return false
    }

    /// SwiftUI's Enter Full Screen command does not use `toggleFullScreen:`.
    /// If we filled the gap first, drop our native extra once SwiftUI's item appears.
    static func dedupeFullScreenItems(in mainMenu: NSMenu) {
        let matches = fullScreenItems(in: mainMenu)
        guard matches.count > 1 else { return }
        let keep = matches.first { $0.item.action != #selector(NSWindow.toggleFullScreen(_:)) } ?? matches[0]
        for match in matches where match.item !== keep.item {
            match.menu.removeItem(match.item)
        }
    }

    private static func fullScreenItems(in menu: NSMenu) -> [(menu: NSMenu, item: NSMenuItem)] {
        var found: [(menu: NSMenu, item: NSMenuItem)] = []
        for item in menu.items {
            let isFullScreen = item.action == #selector(NSWindow.toggleFullScreen(_:))
                || item.title.localizedCaseInsensitiveContains("Full Screen")
                || (
                    item.keyEquivalent.lowercased() == "f"
                        && sameModifiers(item.keyEquivalentModifierMask, [.control, .command])
                )
            if isFullScreen {
                found.append((menu, item))
            }
            if let submenu = item.submenu {
                found.append(contentsOf: fullScreenItems(in: submenu))
            }
        }
        return found
    }

    private static func add(_ need: MenuItemNeed, to mainMenu: NSMenu) {
        let menu = submenu(titled: need.menuTitle, in: mainMenu)
        let item = NSMenuItem(
            title: need.title,
            action: need.action,
            keyEquivalent: need.keyEquivalent
        )
        item.keyEquivalentModifierMask = need.keyEquivalentModifierMask
        item.target = nil
        switch need.action {
        case #selector(NSWindow.performMiniaturize(_:)):
            menu.insertItem(item, at: 0)
        case #selector(NSWindow.performZoom(_:)):
            let afterMinimize = menu.items.firstIndex {
                $0.action == #selector(NSWindow.performMiniaturize(_:))
            }.map { $0 + 1 } ?? 0
            menu.insertItem(item, at: min(afterMinimize, menu.items.count))
        case #selector(NSWindow.toggleFullScreen(_:)),
             #selector(NSApplication.arrangeInFront(_:)):
            appendWithSeparator(item, to: menu)
        default:
            menu.addItem(item)
        }
    }

    private static func appendWithSeparator(_ item: NSMenuItem, to menu: NSMenu) {
        if !menu.items.isEmpty, menu.items.last?.isSeparatorItem != true {
            menu.addItem(.separator())
        }
        menu.addItem(item)
    }

    private static func submenu(titled title: String, in mainMenu: NSMenu) -> NSMenu {
        if let existing = mainMenu.items.first(where: { $0.title == title })?.submenu {
            return existing
        }
        if title == "RunSpecimen" {
            if let first = mainMenu.items.first, let submenu = first.submenu,
               !["File", "Edit", "View", "Window", "Help"].contains(first.title) {
                return submenu
            }
        }
        let item = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        let menu = NSMenu(title: title)
        item.submenu = menu
        let before = title == "View" ? ["Window", "Help"] : title == "Window" ? ["Help"] : []
        if title == "RunSpecimen" {
            mainMenu.insertItem(item, at: 0)
        } else if let index = mainMenu.items.firstIndex(where: { before.contains($0.title) }) {
            mainMenu.insertItem(item, at: index)
        } else {
            mainMenu.addItem(item)
        }
        return menu
    }

    private static func observeMainMenu() {
        if mainMenuObservation == nil {
            mainMenuObservation = NSApp.observe(\.mainMenu, options: [.new]) { _, _ in
                DispatchQueue.main.async { install(into: NSApp.mainMenu) }
            }
        }
        guard observers.isEmpty else { return }
        observers.append(
            NotificationCenter.default.addObserver(
                forName: NSWindow.didBecomeKeyNotification,
                object: nil,
                queue: .main
            ) { _ in
                install(into: NSApp.mainMenu)
            }
        )
    }

    private static func installEscapeMonitor() {
        guard escapeMonitor == nil else { return }
        escapeMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            let window = event.window ?? NSApp.keyWindow
            let shouldExit = shouldExitFullScreenOnEscape(
                keyCode: event.keyCode,
                modifierFlags: event.modifierFlags,
                isFullScreen: window?.styleMask.contains(.fullScreen) == true,
                hasSheet: window?.attachedSheet != nil,
                hasModalWindow: NSApp.modalWindow != nil,
                hasPopupMenu: NSApp.windows.contains { $0.level == .popUpMenu }
            )
            guard shouldExit, let window else { return event }
            window.toggleFullScreen(nil)
            return nil
        }
    }
}

/// Tracks native Full Screen so the View menu title can toggle.
final class FullScreenSession: ObservableObject {
    static let shared = FullScreenSession()

    @Published var isFullScreen = false

    private var observers: [NSObjectProtocol] = []

    func start() {
        guard observers.isEmpty else { return }
        let center = NotificationCenter.default
        observers.append(center.addObserver(forName: NSWindow.didEnterFullScreenNotification, object: nil, queue: .main) { [weak self] note in
            guard let window = note.object as? NSWindow, WindowSanitizer.isMainWindow(window) else { return }
            self?.isFullScreen = true
        })
        observers.append(center.addObserver(forName: NSWindow.didExitFullScreenNotification, object: nil, queue: .main) { [weak self] note in
            guard let window = note.object as? NSWindow, WindowSanitizer.isMainWindow(window) else { return }
            self?.isFullScreen = false
        })
        syncFromKeyWindow()
    }

    func syncFromKeyWindow() {
        if let window = NSApp.windows.first(where: { WindowSanitizer.isMainWindow($0) }) {
            isFullScreen = window.styleMask.contains(.fullScreen)
        }
    }
}
