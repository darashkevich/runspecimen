// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "RunSpecimenApp",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "RunSpecimen", targets: ["RunSpecimenApp"])
    ],
    targets: [
        .executableTarget(
            name: "RunSpecimenApp",
            path: "Sources/RunSpecimenApp"
        )
    ]
)
