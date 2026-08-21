package com.sarvamula.reader;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // must be registered BEFORE super.onCreate — the bridge is built there and only sees
        // plugins already registered. SvPrint gives the reader's "PDF" buttons a print dialog;
        // window.print() is a no-op inside a WebView.
        registerPlugin(SvPrint.class);
        super.onCreate(savedInstanceState);
    }
}
