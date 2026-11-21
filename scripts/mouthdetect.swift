// Find the mouth and chin of every face in each .png/.jpg of a folder with Apple Vision.
// Usage: mouthdetect <dir>  -> prints JSON {"frame.png": [{"face": [x,y,w,h], "lips": [x,y,w,h], "chin": y}, ...]}
// Fractions of the image, origin top-left. "chin" is the lowest point of the face contour.
// Used by capqc.py to check that no caption sits over the speaker's mouth or chin.
import Foundation
import Vision
import AppKit

let dir = URL(fileURLWithPath: CommandLine.arguments[1])
let files = try FileManager.default.contentsOfDirectory(atPath: dir.path)
    .filter { $0.hasSuffix(".png") || $0.hasSuffix(".jpg") }.sorted()

func bounds(_ pts: [CGPoint], _ W: Double, _ H: Double) -> [Double] {
    let xs = pts.map { Double($0.x) }, ys = pts.map { H - Double($0.y) }   // flip to top-left
    let x0 = xs.min()!, x1 = xs.max()!, y0 = ys.min()!, y1 = ys.max()!
    return [x0 / W, y0 / H, (x1 - x0) / W, (y1 - y0) / H]
}

var out: [String: [[String: Any]]] = [:]
for name in files {
    guard let img = NSImage(contentsOf: dir.appendingPathComponent(name)),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    let W = Double(cg.width), H = Double(cg.height)
    let req = VNDetectFaceLandmarksRequest()
    try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
    var faces: [[String: Any]] = []
    for face in req.results ?? [] {
        let b = face.boundingBox
        var row: [String: Any] = ["face": [Double(b.minX), 1 - Double(b.maxY), Double(b.width), Double(b.height)]]
        let size = CGSize(width: W, height: H)
        if let lips = face.landmarks?.outerLips?.pointsInImage(imageSize: size), !lips.isEmpty {
            row["lips"] = bounds(lips, W, H)
        }
        if let contour = face.landmarks?.faceContour?.pointsInImage(imageSize: size), !contour.isEmpty {
            row["chin"] = contour.map { (H - Double($0.y)) / H }.max()!
        }
        faces.append(row)
    }
    out[name] = faces
}
let data = try JSONSerialization.data(withJSONObject: out, options: [.sortedKeys])
print(String(data: data, encoding: .utf8)!)
