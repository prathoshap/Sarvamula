import Foundation
import UIKit
import WebKit
import Capacitor

/// Hands the WKWebView to iOS's print system, whose sheet offers "Save to Files" / AirPrint.
///
/// The reader's PDF buttons called window.print(), which Mobile Safari implements but
/// WKWebView inside an app does not — so the buttons did nothing at all in the app while
/// working on the web.
///
/// `viewPrintFormatter()` is used rather than `UIMarkupTextPrintFormatter`: the markup
/// formatter renders the HTML without the bundle's woff2 faces, which breaks Devanagari
/// shaping — the exact failure a JS PDF library would cause and the reason printing goes
/// through the platform at all. The view formatter prints what the WebView has already laid
/// out, so #printroot and the @media print rules apply unchanged.
@objc(SvPrint)
public class SvPrint: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "SvPrint"
    public let jsName = "SvPrint"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "printDoc", returnType: CAPPluginReturnPromise)
    ]

    // NOT named `print`: that would shadow Swift's global print(_:) inside this type.
    @objc func printDoc(_ call: CAPPluginCall) {
        let jobName = call.getString("name") ?? "Sarvamūla"
        DispatchQueue.main.async {
            guard let web = self.bridge?.webView else {
                call.reject("no webview")
                return
            }
            let info = UIPrintInfo(dictionary: nil)
            info.outputType = .general
            info.jobName = jobName
            let controller = UIPrintInteractionController.shared
            controller.printInfo = info
            controller.printFormatter = web.viewPrintFormatter()
            controller.present(animated: true) { (_, completed, error) in
                if let error = error {
                    call.reject(error.localizedDescription)
                } else {
                    // `completed` is false when the sheet is dismissed without printing —
                    // not an error, and the caller uses it only to clear the print layout.
                    call.resolve(["completed": completed])
                }
            }
        }
    }
}
