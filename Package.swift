// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "TVRemote",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(name: "TVRemote", path: "Sources/TVRemote"),
        // Tests import the app module with @testable, so the model structs stay internal.
        .testTarget(name: "TVRemoteTests", dependencies: ["TVRemote"], path: "Tests/TVRemoteTests",
                    resources: [.copy("Fixtures")]),
    ]
)
