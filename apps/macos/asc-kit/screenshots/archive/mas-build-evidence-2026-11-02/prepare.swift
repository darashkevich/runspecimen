import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

let inputRoot = URL(fileURLWithPath: "/tmp/rs-asc-mas-20261102")
let outputRoot = URL(fileURLWithPath: "/Users/yahor/runspecimen/apps/macos/asc-kit/screenshots")
let entries: [(String,String,Int,Int,Double)] = [
 ("01-main-raw.png", "01-main.png", 56, 0, 1.0),
 ("02-doctor-raw.png", "02-doctor.png", 56, 0, 1.0),
 ("03-approve-raw.png", "03-approve.png", 24, 0, 1.5),
 ("04-dashboard-raw.png", "04-dashboard.png", 56, 0, 1.0),
 ("05-settings-raw.png", "05-settings.png", 24, 0, 1.0)
]
let space = CGColorSpace(name: CGColorSpace.sRGB)!
for (sourceName, outputName, top, bottom, maximumScale) in entries {
 let source = CGImageSourceCreateWithURL(inputRoot.appendingPathComponent(sourceName) as CFURL, nil)!
 let image = CGImageSourceCreateImageAtIndex(source, 0, nil)!
 let width = image.width, height = image.height-top-bottom
 let cropped = image.cropping(to: CGRect(x:0,y:top,width:width,height:height))!
 let scale = min(maximumScale, min(2660.0/Double(width),1640.0/Double(height)))
 let drawWidth = Int((Double(width)*scale).rounded()), drawHeight = Int((Double(height)*scale).rounded())
 let context = CGContext(data:nil,width:2880,height:1800,bitsPerComponent:8,bytesPerRow:0,space:space,bitmapInfo:CGImageAlphaInfo.noneSkipLast.rawValue)!
 context.setFillColor(CGColor(colorSpace:space,components:[17.0/255,22.0/255,31.0/255,1])!)
 context.fill(CGRect(x:0,y:0,width:2880,height:1800))
 context.interpolationQuality = .high
 let bounds = CGRect(x:(2880-drawWidth)/2,y:(1800-drawHeight)/2,width:drawWidth,height:drawHeight)
 context.saveGState()
 if true {
  context.addPath(CGPath(roundedRect:bounds,cornerWidth:48*scale,cornerHeight:48*scale,transform:nil))
  context.clip()
 }
 context.draw(cropped,in:bounds)
 context.restoreGState()
 let result = context.makeImage()!
 let destination = CGImageDestinationCreateWithURL(outputRoot.appendingPathComponent(outputName) as CFURL, UTType.png.identifier as CFString, 1, nil)!
 let properties: [CFString:Any] = [kCGImagePropertyPNGDictionary:[kCGImagePropertyPNGsRGBIntent:0]]
 CGImageDestinationAddImage(destination,result,properties as CFDictionary)
 precondition(CGImageDestinationFinalize(destination))
 print("\(outputName): 2880x1800, sRGB, RGB opaque; source \(width)x\(height), displayed \(drawWidth)x\(drawHeight)")
}
