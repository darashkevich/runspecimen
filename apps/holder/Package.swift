// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "HolderSocket",
    platforms: [.macOS(.v13)],
    targets: [
        .target(name: "HolderSocket", path: "Sources/HolderSocket"),
        .target(name: "DaemonKeyFeasibility", path: "Sources/DaemonKeyFeasibility"),
        .testTarget(
            name: "HolderSocketTests",
            dependencies: ["HolderSocket"],
            path: "Tests/HolderSocketTests"
        ),
        .testTarget(
            name: "DaemonKeyFeasibilityTests",
            dependencies: ["DaemonKeyFeasibility"],
            path: "Tests/DaemonKeyFeasibilityTests"
        ),
    ]
)
