// Detect faces in every .jpg of a folder with Apple Vision (offline, on-device).
// Usage: facedetect <dir> [grid]  -> prints JSON {"frame.jpg": [[x, y, w, h, conf], ...]}
// Boxes are fractions of the image, origin top-left. Vision misses small crowd faces on
// the full frame, so it also scans overlapping tiles (1x1, 2x2 and grid x grid) and merges.
import Foundation
import Vision
import AppKit

let dir = URL(fileURLWithPath: CommandLine.arguments[1])
let grid = CommandLine.arguments.count > 2 ? Int(CommandLine.arguments[2]) ?? 4 : 4
let minConf: Float = 0.5
let files = try FileManager.default.contentsOfDirectory(atPath: dir.path)
    .filter { $0.hasSuffix(".jpg") }.sorted()

func tiles(_ n: Int) -> [CGRect] {
    let size = min(1.0, 1.5 / Double(n))      // 50% overlap between neighbours
    let step = n > 1 ? (1.0 - size) / Double(n - 1) : 0
    return (0..<n).flatMap { i in (0..<n).map { j in
        CGRect(x: Double(i) * step, y: Double(j) * step, width: size, height: size) } }
}

func iou(_ a: [Double], _ b: [Double]) -> Double {
    let x1 = max(a[0], b[0]), y1 = max(a[1], b[1])
    let x2 = min(a[0] + a[2], b[0] + b[2]), y2 = min(a[1] + a[3], b[1] + b[3])
    let inter = max(0, x2 - x1) * max(0, y2 - y1)
    return inter / min(a[2] * a[3], b[2] * b[3])
}

var out: [String: [[Double]]] = [:]
for name in files {
    guard let img = NSImage(contentsOf: dir.appendingPathComponent(name)),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    var found: [[Double]] = []
    for roi in tiles(1) + tiles(2) + tiles(3) + (grid > 3 ? tiles(grid) : []) {
        // Crop the tile for real (ROI alone keeps Vision's downscale), top-left origin.
        let W = Double(cg.width), H = Double(cg.height)
        let px = CGRect(x: roi.minX * W, y: roi.minY * H, width: roi.width * W, height: roi.height * H).integral
        guard let tile = cg.cropping(to: px) else { continue }
        let req = VNDetectFaceRectanglesRequest()
        let body = VNDetectHumanRectanglesRequest()
        body.upperBodyOnly = true
        try VNImageRequestHandler(cgImage: tile, options: [:]).perform([req, body])
        // A head is the top of an upper-body box: covers faces turned away or too small
        // for the face model. Tagged with conf 2+ so callers can tell the two apart.
        for h in body.results ?? [] where h.confidence >= minConf {
            let b = h.boundingBox
            let hw = b.width * 0.62, hh = min(b.height * 0.5, hw * 1.3 * px.width / px.height)
            let x = (px.minX + (b.midX - hw / 2) * px.width) / W
            let y = (px.minY + (1 - b.maxY) * px.height) / H
            found.append([x, y, hw * px.width / W, hh * px.height / H, 2 + Double(h.confidence)])
        }
        for f in req.results ?? [] where f.confidence >= minConf {
            let b = f.boundingBox   // normalized to the tile, origin bottom-left
            let x = (px.minX + b.minX * px.width) / W
            let y = (px.minY + (1 - b.maxY) * px.height) / H
            found.append([x, y, b.width * px.width / W, b.height * px.height / H, Double(f.confidence)])
        }
    }
    var kept: [[Double]] = []
    for box in found.sorted(by: { $0[4] > $1[4] }) where !kept.contains(where: { iou($0, box) > 0.4 }) {
        kept.append(box)
    }
    out[name] = kept
}
let data = try JSONSerialization.data(withJSONObject: out, options: [.sortedKeys])
print(String(data: data, encoding: .utf8)!)
