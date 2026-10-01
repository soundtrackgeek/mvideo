import AppKit
import Foundation

let root = URL(fileURLWithPath: CommandLine.arguments[1])
let info: [String: Any] = ["author": "xcode", "version": 1]
func json(_ value: [String: Any], _ directory: URL) throws {
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    try JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys]).write(to: directory.appendingPathComponent("Contents.json"))
}
func render(_ width: Int, _ height: Int, layer: String, to path: URL) throws {
    let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState(); NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
    let rect = NSRect(x: 0, y: 0, width: width, height: height)
    NSColor.clear.setFill(); rect.fill()
    if layer != "front" {
        NSColor(calibratedRed: 0.035, green: 0.043, blue: 0.047, alpha: 1).setFill(); rect.fill()
        let gradient = NSGradient(starting: NSColor(calibratedRed: 0.19, green: 0.16, blue: 0.12, alpha: 1), ending: NSColor(calibratedRed: 0.035, green: 0.043, blue: 0.047, alpha: 1))!
        gradient.draw(in: rect, angle: 140)
    }
    if layer != "back" {
        let font = NSFont.systemFont(ofSize: CGFloat(height) * 0.24, weight: .bold)
        let text = NSAttributedString(string: "mvideo", attributes: [.font: font, .foregroundColor: NSColor(calibratedRed: 0.96, green: 0.945, blue: 0.91, alpha: 1)])
        let size = text.size(); text.draw(at: NSPoint(x: (CGFloat(width)-size.width)/2, y: (CGFloat(height)-size.height)/2 + CGFloat(height)*0.02))
        NSColor(calibratedRed: 0.98, green: 0.73, blue: 0.38, alpha: 1).setFill()
        NSBezierPath(roundedRect: NSRect(x: CGFloat(width)*0.43, y: CGFloat(height)*0.29, width: CGFloat(width)*0.14, height: CGFloat(height)*0.013), xRadius: 3, yRadius: 3).fill()
    }
    NSGraphicsContext.restoreGraphicsState()
    try bitmap.representation(using: .png, properties: [:])!.write(to: path)
}
try json(["info": info], root)
let brand = root.appendingPathComponent("App Icon & Top Shelf Image.brandassets")
var assets: [[String: Any]] = []
for (name, width, height, role) in [("App Icon",400,240,"primary-app-icon"),("App Icon - App Store",1280,768,"primary-app-icon")] {
    let stack = brand.appendingPathComponent(name+".imagestack")
    try json(["info": info, "layers": [["filename":"Front.imagestacklayer"],["filename":"Back.imagestacklayer"]]],stack)
    for layer in ["Front","Back"] {
        let dir = stack.appendingPathComponent(layer+".imagestacklayer")
        try json(["info": info],dir)
        let content = dir.appendingPathComponent("Content.imageset")
        var images: [[String:Any]] = []
        for scale in (width == 400 ? [1,2] : [1]) {
            images.append(["filename":"\(scale)x.png","idiom":"tv","scale":"\(scale)x"])
        }
        try json(["info":info,"images":images],content)
        for scale in (width == 400 ? [1,2] : [1]) { try render(width*scale,height*scale,layer:layer.lowercased(),to:content.appendingPathComponent("\(scale)x.png")) }
    }
    assets.append(["filename":name+".imagestack","idiom":"tv","role":role,"size":"\(width)x\(height)"])
}
for (name,width,role) in [("Top Shelf Image",1920,"top-shelf-image"),("Top Shelf Image Wide",2320,"top-shelf-image-wide")] {
    let content = brand.appendingPathComponent(name+".imageset")
    try json(["info":info,"images":[["filename":"1x.png","idiom":"tv","scale":"1x"],["filename":"2x.png","idiom":"tv","scale":"2x"]]],content)
    for scale in [1,2] { try render(width*scale,720*scale,layer:"full",to:content.appendingPathComponent("\(scale)x.png")) }
    assets.append(["filename":name+".imageset","idiom":"tv","role":role,"size":"\(width)x720"])
}
try json(["info":info,"assets":assets],brand)
