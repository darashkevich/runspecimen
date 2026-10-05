// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "RunSpecimenApp",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .library(name: "RunSpecimenCore", targets: ["RunSpecimenCore"]),
        .executable(name: "RunSpecimen", targets: ["RunSpecimenApp"]),
        .executable(name: "RunSpecimenTouchIDDiagnostic", targets: ["RunSpecimenTouchIDDiagnostic"])
    ],
    targets: [
        .target(
            name: "RunSpecimenCore",
            path: "Sources/RunSpecimenCore",
            swiftSettings: [
                // Debug is what `swift test` compiles. The Xcode Store target
                // does not use this setting, so Release and Debug archives omit it.
                .define("RUNSPECIMEN_TEST_HOOKS", .when(configuration: .debug))
            ]
        ),
        .executableTarget(
            name: "RunSpecimenApp",
            dependencies: ["RunSpecimenCore"],
            path: "Sources/RunSpecimenApp"
        ),
        .executableTarget(
            name: "RunSpecimenTouchIDDiagnostic",
            dependencies: ["RunSpecimenCore"],
            path: "Sources/RunSpecimenTouchIDDiagnostic"
        ),
        .testTarget(
            name: "RunSpecimenCoreTests",
            dependencies: ["RunSpecimenCore"],
            path: "Tests/RunSpecimenCoreTests"
        ),
        .testTarget(
            name: "RunSpecimenAppTests",
            dependencies: ["RunSpecimenApp", "RunSpecimenCore"],
            path: "Tests/RunSpecimenAppTests"
        )
    ]
)
