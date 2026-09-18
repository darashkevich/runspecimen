import CoreGraphics
import Foundation

/// Pure-geometry clamp for the native SwiftUI window.
///
/// `WindowGroup` + unbounded `Spacer` can ask for a multi-thousand-point frame,
/// which AppKit then places off-screen. Full Screen is disabled for those
/// windows. Frames use AppKit coordinates (origin bottom-left).
public enum WindowPlacement {
    /// Fits 13-inch laptops and Stage Manager / split tiles; SwiftUI can grow from here.
    public static let minSize = CGSize(width: 720, height: 520)
    public static let defaultSize = CGSize(width: 1180, height: 760)

    public static func area(_ rect: CGRect) -> CGFloat {
        max(0, rect.width) * max(0, rect.height)
    }

    /// True when the frame is off every screen, or larger than the display.
    public static func needsSanitize(frame: CGRect, screens: [CGRect]) -> Bool {
        guard !screens.isEmpty else { return false }
        guard let screen = bestScreen(for: frame, screens: screens) else { return true }
        let visible = area(frame.intersection(screen))
        let wanted = max(area(frame), 1)
        if visible < min(80_000, wanted * 0.2) {
            return true
        }
        // Full-screen / zoomed frames can exceed visibleFrame slightly; 1.2
        // catches the Spacer-driven 5000pt windows without fighting Full Screen.
        if frame.height > screen.height * 1.2 || frame.width > screen.width * 1.2 {
            return true
        }
        if frame.width + 0.5 < minSize.width || frame.height + 0.5 < minSize.height {
            return true
        }
        return false
    }

    public static func sanitize(
        frame: CGRect,
        screens: [CGRect],
        defaultSize: CGSize = defaultSize,
        minSize: CGSize = minSize
    ) -> CGRect {
        guard let screen = bestScreen(for: frame, screens: screens) ?? screens.first else {
            return CGRect(origin: frame.origin, size: defaultSize)
        }

        var size = frame.size
        let insane =
            frame.height > screen.height * 1.1
            || frame.width > screen.width * 1.5
            || area(frame.intersection(screen)) < 80_000

        if insane {
            size.width = min(defaultSize.width, screen.width)
            size.height = min(defaultSize.height, screen.height)
        }

        size.width = min(max(size.width, minSize.width), screen.width)
        size.height = min(max(size.height, minSize.height), screen.height)
        size.width = min(size.width, screen.width)
        size.height = min(size.height, screen.height)

        var origin = frame.origin
        if insane || area(CGRect(origin: origin, size: size).intersection(screen)) < 80_000 {
            origin.x = screen.midX - size.width / 2
            origin.y = screen.midY - size.height / 2
        }

        if origin.x + size.width > screen.maxX {
            origin.x = screen.maxX - size.width
        }
        if origin.x < screen.minX {
            origin.x = screen.minX
        }
        if origin.y + size.height > screen.maxY {
            origin.y = screen.maxY - size.height
        }
        if origin.y < screen.minY {
            origin.y = screen.minY
        }

        return CGRect(origin: origin, size: size)
    }

    public static func bestScreen(for frame: CGRect, screens: [CGRect]) -> CGRect? {
        screens.max { lhs, rhs in
            area(lhs.intersection(frame)) < area(rhs.intersection(frame))
        }
    }
}
