import Vision
import AppKit
import CoreImage

let args = CommandLine.arguments
guard args.count == 3 else { print("usage: segment <in> <out>"); exit(1) }
let url = URL(fileURLWithPath: args[1])
guard let ciImage = CIImage(contentsOf: url) else { print("load failed"); exit(1) }
let request = VNGenerateForegroundInstanceMaskRequest()
let handler = VNImageRequestHandler(ciImage: ciImage)
try handler.perform([request])
guard let result = request.results?.first else { print("no foreground found"); exit(1) }
let maskedBuffer = try result.generateMaskedImage(ofInstances: result.allInstances, from: handler, croppedToInstancesExtent: false)
let masked = CIImage(cvPixelBuffer: maskedBuffer)
let ctx = CIContext()
guard let png = ctx.pngRepresentation(of: masked, format: .RGBA8, colorSpace: CGColorSpace(name: CGColorSpace.sRGB)!) else { print("encode failed"); exit(1) }
try png.write(to: URL(fileURLWithPath: args[2]))
print("segmented ok")
