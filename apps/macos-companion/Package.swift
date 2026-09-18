// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "RunSpecimenMacCompanion",
    platforms: [
        .macOS(.v14),
    ],
    products: [
        .library(name: "RunSpecimenMacCompanion", targets: ["RunSpecimenMacCompanion"]),
        .executable(name: "runspecimen-companion-ui", targets: ["RunSpecimenCompanionUI"]),
    ],
    targets: [
        .target(
            name: "RunSpecimenMacCompanion",
            path: "Sources/RunSpecimenMacCompanion"
        ),
        .executableTarget(
            name: "RunSpecimenCompanionUI",
            dependencies: ["RunSpecimenMacCompanion"],
            path: "Sources/RunSpecimenCompanionUI",
            exclude: ["Info.plist"]
        ),
        .testTarget(
            name: "RunSpecimenMacCompanionTests",
            dependencies: ["RunSpecimenMacCompanion"],
            path: "Tests/RunSpecimenMacCompanionTests"
        ),
    ]
)
