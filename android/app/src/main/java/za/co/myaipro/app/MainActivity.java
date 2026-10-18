package za.co.myaipro.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Intent;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Bundle;
import android.view.KeyEvent;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

/**
 * My AI Pro - native Android shell for https://my-ai-pro-rkxe.onrender.com
 * A single full-screen WebView with everything the web app needs:
 * JavaScript, DOM storage (chat history + allowance), file uploads,
 * downloads, back navigation and an offline/error notice.
 */
public class MainActivity extends Activity {

    private static final String HOME = "https://my-ai-pro-rkxe.onrender.com/";
    private static final int FILE_CHOOSER_REQ = 7001;

    private WebView web;
    private ValueCallback<Uri[]> fileCallback;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        web = new WebView(this);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setMediaPlaybackRequiresUserGesture(true);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setUserAgentString(s.getUserAgentString() + " MyAIProAndroid/1.0");

        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                Uri url = req.getUrl();
                if ("https".equals(url.getScheme()) && url.getHost() != null
                        && url.getHost().endsWith("my-ai-pro-rkxe.onrender.com")) {
                    return false;                       // stay inside the app
                }
                startActivity(new Intent(Intent.ACTION_VIEW, url));   // everything else: browser
                return true;
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                                             FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                Intent pick = new Intent(Intent.ACTION_GET_CONTENT);
                pick.addCategory(Intent.CATEGORY_OPENABLE);
                pick.setType("*/*");
                startActivityForResult(Intent.createChooser(pick, "Attach a file"), FILE_CHOOSER_REQ);
                return true;
            }
        });

        web.setDownloadListener((url, ua, contentDisposition, mime, length) ->
                startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url))));

        if (saved == null) web.loadUrl(HOME);
        else restore();
    }

    private void restore() {
        try {
            web.restoreState(getIntent().getExtras() != null
                    ? getIntent().getExtras() : new Bundle());
        } catch (Exception e) {
            web.loadUrl(HOME);
        }
        if (web.getUrl() == null) web.loadUrl(HOME);
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        if (req == FILE_CHOOSER_REQ) {
            Uri[] result = null;
            if (res == RESULT_OK && data != null && data.getData() != null) {
                result = new Uri[]{data.getData()};
            }
            if (fileCallback != null) fileCallback.onReceiveValue(result);
            fileCallback = null;
        } else {
            super.onActivityResult(req, res, data);
        }
    }

    @Override
    public boolean onKeyDown(int code, KeyEvent event) {
        if (code == KeyEvent.KEYCODE_BACK && web.canGoBack()) {
            web.goBack();
            return true;
        }
        return super.onKeyDown(code, event);
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
    }

    @Override
    protected void onPause() {
        web.onPause();
        super.onPause();
    }
}
