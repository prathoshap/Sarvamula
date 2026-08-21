package com.sarvamula.reader;

import android.content.Context;
import android.print.PrintAttributes;
import android.print.PrintDocumentAdapter;
import android.print.PrintManager;
import android.webkit.WebView;

import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * Hands the WebView to Android's print framework, whose dialog offers "Save as PDF".
 *
 * The reader's PDF buttons called window.print(), which Mobile Safari and desktop browsers
 * implement but Android WebView and iOS WKWebView do NOT — so in the apps the buttons did
 * nothing at all, silently, while working fine on the web.
 *
 * Printing goes through the platform rather than a JS PDF library on purpose: jsPDF and
 * pdfmake place glyphs with no shaping engine, so Devanagari conjuncts and mātrās break —
 * unacceptable for a critical edition. The WebView's own text stack shapes correctly, and
 * createPrintDocumentAdapter applies the page's @media print rules, so #printroot and the
 * existing print stylesheet are used unchanged.
 */
@CapacitorPlugin(name = "SvPrint")
public class SvPrint extends Plugin {

    @PluginMethod
    public void printDoc(final PluginCall call) {
        final String jobName = call.getString("name", "Sarvamula");
        // must run on the UI thread: the adapter is created from the WebView
        getActivity().runOnUiThread(new Runnable() {
            @Override
            public void run() {
                try {
                    WebView web = getBridge().getWebView();
                    if (web == null) {
                        call.reject("no webview");
                        return;
                    }
                    PrintManager pm = (PrintManager)
                            getActivity().getSystemService(Context.PRINT_SERVICE);
                    if (pm == null) {
                        call.reject("printing unavailable");
                        return;
                    }
                    PrintDocumentAdapter adapter = web.createPrintDocumentAdapter(jobName);
                    pm.print(jobName, adapter, new PrintAttributes.Builder().build());
                    call.resolve();
                } catch (Exception e) {
                    call.reject(e.getMessage(), e);
                }
            }
        });
    }
}
