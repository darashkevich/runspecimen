// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "RunSpecimenApp",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .library(name: "RunSpecimenCore", targets: ["RunSpecimenCore"]),
        .executable(name: "RunSpecimen", targets: ["RunSpecimenApp"])
    ],
    targets: [
        .target(
            name: "RunSpecimenCore",
            path: "Sources/RunSpecimenCore"
        ),
        .executableTarget(
            name: "RunSpecimenApp",
            dependencies: ["RunSpecimenCore"],
            path: "Sources/RunSpecimenApp"
        ),
        .testTarget(
            name: "RunSpecimenCoreTests",
            dependencies: ["RunSpecimenCore"],
            path: "Tests/RunSpecimenCoreTests"
        )
    ]
)
