// Body pose + person matte for every .jpg of a folder with Apple Vision (offline, on-device).
// Usage: bodytrack <dir> <maskdir>  -> prints JSON {"frame.jpg": [{"joint": [x, y, conf], ...}, ...]}
// with one joint map per person found. Joints are fractions of the image, origin top-left. Writes <maskdir>/<frame>.png, the
// person segmentation matte (accurate quality) at the source frame size.
import Foundation
import Vision
import AppKit
import CoreImage

let dir = URL(fileURLWithPath: CommandLine.arguments[1])
let maskDir = URL(fileURLWithPath: CommandLine.arguments[2])
try FileManager.default.createDirectory(at: maskDir, withIntermediateDirectories: true)
let files = try FileManager.default.contentsOfDirectory(atPath: dir.path)
    .filter { $0.hasSuffix(".jpg") }.sorted()
let ctx = CIContext()

var out: [String: [[String: [Double]]]] = [:]
for name in files {
    guard let img = NSImage(contentsOf: dir.appendingPathComponent(name)),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    let pose = VNDetectHumanBodyPoseRequest()
    let seg = VNGeneratePersonSegmentationRequest()
    seg.qualityLevel = .accurate
    seg.outputPixelFormat = kCVPixelFormatType_OneComponent8
    try VNImageRequestHandler(cgImage: cg, options: [:]).perform([pose, seg])

    var people: [[String: [Double]]] = []
    for body in pose.results ?? [] {
        guard let pts = try? body.recognizedPoints(.all) else { continue }
        var joints: [String: [Double]] = [:]
        for (key, p) in pts where p.confidence > 0.1 {
            joints[key.rawValue.rawValue] = [Double(p.location.x), 1 - Double(p.location.y), Double(p.confidence)]
        }
        if !joints.isEmpty { people.append(joints) }
    }
    out[name] = people

    if let buf = seg.results?.first?.pixelBuffer {
        var matte = CIImage(cvPixelBuffer: buf)
        let sx = CGFloat(cg.width) / matte.extent.width, sy = CGFloat(cg.height) / matte.extent.height
        matte = matte.transformed(by: CGAffineTransform(scaleX: sx, y: sy))
        let png = maskDir.appendingPathComponent((name as NSString).deletingPathExtension + ".png")
        try ctx.writePNGRepresentation(of: matte, to: png, format: .L8,
                                       colorSpace: CGColorSpace(name: CGColorSpace.linearGray)!)
    }
}
let data = try JSONSerialization.data(withJSONObject: out, options: [.sortedKeys])
print(String(data: data, encoding: .utf8)!)
