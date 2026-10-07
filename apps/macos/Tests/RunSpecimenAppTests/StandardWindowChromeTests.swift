import AppKit
import XCTest
@testable import RunSpecimenApp

final class StandardWindowChromeTests: XCTestCase {
    func testEmptyMenuGetsStandardWindowItems() {
        let menu = NSMenu(title: "MainMenu")
        StandardWindowChrome.install(into: menu)

        XCTAssertTrue(StandardWindowChrome.missingItems(in: menu).isEmpty, "installer should fill every standard gap")

        let fullScreen = item(in: menu, titled: "Enter Full Screen")
        XCTAssertEqual(fullScreen?.action, #selector(NSWindow.toggleFullScreen(_:)))
        XCTAssertEqual(fullScreen?.keyEquivalent.lowercased(), "f")
        XCTAssertTrue(
            StandardWindowChrome.sameModifiers(fullScreen?.keyEquivalentModifierMask ?? [], [.control, .command])
        )

        let minimize = item(in: menu, titled: "Minimize")
        XCTAssertEqual(minimize?.action, #selector(NSWindow.performMiniaturize(_:)))
        XCTAssertEqual(minimize?.keyEquivalent.lowercased(), "m")
        XCTAssertTrue(StandardWindowChrome.sameModifiers(minimize?.keyEquivalentModifierMask ?? [], [.command]))

        XCTAssertEqual(item(in: menu, titled: "Zoom")?.action, #selector(NSWindow.performZoom(_:)))
        XCTAssertEqual(item(in: menu, titled: "Bring All to Front")?.action, #selector(NSApplication.arrangeInFront(_:)))
        XCTAssertEqual(item(in: menu, titled: "Close")?.action, #selector(NSWindow.performClose(_:)))
        XCTAssertEqual(item(in: menu, titled: "Close")?.keyEquivalent.lowercased(), "w")
        XCTAssertEqual(item(in: menu, titled: "Hide RunSpecimen")?.action, #selector(NSApplication.hide(_:)))
        XCTAssertEqual(item(in: menu, titled: "Quit RunSpecimen")?.action, #selector(NSApplication.terminate(_:)))
        XCTAssertEqual(item(in: menu, titled: "Quit RunSpecimen")?.keyEquivalent.lowercased(), "q")
    }

    func testInstallIsIdempotentAndDoesNotDuplicateShortcuts() {
        let menu = NSMenu(title: "MainMenu")
        StandardWindowChrome.install(into: menu)
        StandardWindowChrome.install(into: menu)
        StandardWindowChrome.install(into: menu)

        XCTAssertEqual(count(in: menu, titled: "Enter Full Screen"), 1)
        XCTAssertEqual(count(in: menu, titled: "Minimize"), 1)
        XCTAssertEqual(count(in: menu, titled: "Zoom"), 1)
        XCTAssertEqual(count(in: menu, titled: "Close"), 1)
        XCTAssertEqual(count(in: menu) { $0.keyEquivalent.lowercased() == "f" && StandardWindowChrome.sameModifiers($0.keyEquivalentModifierMask, [.control, .command]) }, 1)
        XCTAssertEqual(count(in: menu) { $0.keyEquivalent.lowercased() == "m" && StandardWindowChrome.sameModifiers($0.keyEquivalentModifierMask, [.command]) }, 1)
        XCTAssertEqual(count(in: menu) { $0.keyEquivalent.lowercased() == "w" && StandardWindowChrome.sameModifiers($0.keyEquivalentModifierMask, [.command]) }, 1)
    }

    func testDedupeKeepsSwiftUIFullScreenItem() {
        let menu = NSMenu(title: "MainMenu")
        let view = NSMenu(title: "View")
        let viewItem = NSMenuItem(title: "View", action: nil, keyEquivalent: "")
        viewItem.submenu = view
        menu.addItem(viewItem)

        let swiftUI = NSMenuItem(title: "Enter Full Screen", action: nil, keyEquivalent: "f")
        swiftUI.keyEquivalentModifierMask = [.control, .command]
        view.addItem(swiftUI)
        let native = NSMenuItem(title: "Enter Full Screen", action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f")
        native.keyEquivalentModifierMask = [.control, .command]
        view.addItem(native)

        StandardWindowChrome.install(into: menu)
        XCTAssertEqual(count(in: menu, titled: "Enter Full Screen"), 1)
        XCTAssertNil(item(in: menu, titled: "Enter Full Screen")?.action)
    }

    func testExistingSwiftUIFullScreenShortcutIsTreatedAsPresent() {
        let menu = NSMenu(title: "MainMenu")
        let view = NSMenu(title: "View")
        let viewItem = NSMenuItem(title: "View", action: nil, keyEquivalent: "")
        viewItem.submenu = view
        menu.addItem(viewItem)

        let existing = NSMenuItem(title: "Enter Full Screen", action: nil, keyEquivalent: "f")
        existing.keyEquivalentModifierMask = [.control, .command]
        view.addItem(existing)

        let missing = StandardWindowChrome.missingItems(in: menu)
        XCTAssertFalse(missing.contains { $0.action == #selector(NSWindow.toggleFullScreen(_:)) })

        StandardWindowChrome.install(into: menu)
        XCTAssertEqual(count(in: menu, titled: "Enter Full Screen"), 1)
        XCTAssertEqual(count(in: menu) { $0.action == #selector(NSWindow.toggleFullScreen(_:)) }, 0)
    }

    func testEscapeExitsFullScreenOnlyForBareEscape() {
        XCTAssertTrue(
            StandardWindowChrome.shouldExitFullScreenOnEscape(
                keyCode: StandardWindowChrome.escapeKeyCode,
                modifierFlags: [],
                isFullScreen: true,
                hasSheet: false,
                hasModalWindow: false,
                hasPopupMenu: false
            )
        )
        XCTAssertFalse(
            StandardWindowChrome.shouldExitFullScreenOnEscape(
                keyCode: StandardWindowChrome.escapeKeyCode,
                modifierFlags: [],
                isFullScreen: false,
                hasSheet: false,
                hasModalWindow: false,
                hasPopupMenu: false
            )
        )
        XCTAssertFalse(
            StandardWindowChrome.shouldExitFullScreenOnEscape(
                keyCode: StandardWindowChrome.escapeKeyCode,
                modifierFlags: [],
                isFullScreen: true,
                hasSheet: true,
                hasModalWindow: false,
                hasPopupMenu: false
            ),
            "sheets keep Esc so Close / Cancel still work"
        )
        XCTAssertFalse(
            StandardWindowChrome.shouldExitFullScreenOnEscape(
                keyCode: StandardWindowChrome.escapeKeyCode,
                modifierFlags: [],
                isFullScreen: true,
                hasSheet: false,
                hasModalWindow: true,
                hasPopupMenu: false
            )
        )
        XCTAssertFalse(
            StandardWindowChrome.shouldExitFullScreenOnEscape(
                keyCode: StandardWindowChrome.escapeKeyCode,
                modifierFlags: [],
                isFullScreen: true,
                hasSheet: false,
                hasModalWindow: false,
                hasPopupMenu: true
            )
        )
        XCTAssertFalse(
            StandardWindowChrome.shouldExitFullScreenOnEscape(
                keyCode: StandardWindowChrome.escapeKeyCode,
                modifierFlags: [.command],
                isFullScreen: true,
                hasSheet: false,
                hasModalWindow: false,
                hasPopupMenu: false
            )
        )
        XCTAssertFalse(
            StandardWindowChrome.shouldExitFullScreenOnEscape(
                keyCode: 0,
                modifierFlags: [],
                isFullScreen: true,
                hasSheet: false,
                hasModalWindow: false,
                hasPopupMenu: false
            )
        )
    }

    func testFrameSanitizeYieldsToNativeFullScreen() {
        XCTAssertTrue(WindowSanitizer.shouldSkipFrameSanitize(isFullScreen: true, isTransitioningToOrFromFullScreen: false))
        XCTAssertTrue(WindowSanitizer.shouldSkipFrameSanitize(isFullScreen: false, isTransitioningToOrFromFullScreen: true))
        XCTAssertFalse(WindowSanitizer.shouldSkipFrameSanitize(isFullScreen: false, isTransitioningToOrFromFullScreen: false))
    }

    private func item(in menu: NSMenu, titled title: String) -> NSMenuItem? {
        var found: NSMenuItem?
        walk(menu) { item in
            if item.title == title { found = item }
        }
        return found
    }

    private func count(in menu: NSMenu, titled title: String) -> Int {
        count(in: menu) { $0.title == title }
    }

    private func count(in menu: NSMenu, where predicate: (NSMenuItem) -> Bool) -> Int {
        var total = 0
        walk(menu) { item in
            if predicate(item) { total += 1 }
        }
        return total
    }

    private func walk(_ menu: NSMenu, _ visit: (NSMenuItem) -> Void) {
        for item in menu.items {
            visit(item)
            if let submenu = item.submenu {
                walk(submenu, visit)
            }
        }
    }
}
