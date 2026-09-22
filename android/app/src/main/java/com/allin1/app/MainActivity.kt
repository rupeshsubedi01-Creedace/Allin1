package com.allin1.app

import android.Manifest
import android.annotation.SuppressLint
import android.app.DownloadManager
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.webkit.CookieManager
import android.webkit.URLUtil
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity

/**
 * Native Android shell around a self-hosted Allin1 server.
 *
 * The Python backend does all the real work (yt-dlp extraction + ffmpeg
 * post-processing). This activity renders the bundled PWA in a WebView and
 * hands finished media to Android's DownloadManager so files land in the
 * device's Downloads folder instead of being trapped in browser storage.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var progressBar: ProgressBar
    private lateinit var setupView: ScrollView
    private lateinit var errorView: ScrollView
    private lateinit var errorBody: TextView
    private lateinit var serverInput: EditText
    private lateinit var connectButton: Button
    private lateinit var retryButton: Button
    private lateinit var changeServerButton: Button

    private val prefs by lazy { getSharedPreferences(PREFS, Context.MODE_PRIVATE) }
    private var serverUrl: String = ""
    private var pendingDownload: PendingDownload? = null

    private data class PendingDownload(
        val url: String,
        val userAgent: String?,
        val contentDisposition: String?,
        val mimeType: String?,
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        webView = findViewById(R.id.web_view)
        progressBar = findViewById(R.id.progress_bar)
        setupView = findViewById(R.id.setup_view)
        errorView = findViewById(R.id.error_view)
        errorBody = findViewById(R.id.error_body)
        serverInput = findViewById(R.id.server_input)
        connectButton = findViewById(R.id.connect_button)
        retryButton = findViewById(R.id.retry_button)
        changeServerButton = findViewById(R.id.change_server_button)

        configureWebView()

        connectButton.setOnClickListener { connectToTypedServer() }
        retryButton.setOnClickListener { loadServer() }
        changeServerButton.setOnClickListener { showSetup() }
        serverInput.setOnEditorActionListener { _, _, _ ->
            connectToTypedServer()
            true
        }

        // Android 13+ needs an explicit grant before DownloadManager can show
        // its "download finished" notification.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQ_NOTIFICATIONS)
        }

        serverUrl = prefs.getString(KEY_SERVER, null)?.takeIf { it.isNotBlank() }
            ?: BuildConfig.DEFAULT_SERVER_URL.trim()

        if (serverUrl.isBlank()) {
            showSetup()
        } else {
            loadServer()
        }
    }

    // ------------------------------------------------------------------ WebView

    @SuppressLint("SetJavaScriptEnabled")
    private fun configureWebView() {
        val settings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.databaseEnabled = true
        settings.loadWithOverviewMode = true
        settings.useWideViewPort = true
        settings.setSupportZoom(true)
        settings.builtInZoomControls = false
        settings.mediaPlaybackRequiresUserGesture = false
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
        // Load target="_blank" links in this WebView rather than spawning a
        // second window we would have to manage.
        settings.setSupportMultipleWindows(false)

        CookieManager.getInstance().setAcceptCookie(true)

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(
                view: WebView,
                request: WebResourceRequest,
            ): Boolean = handleUrl(request.url)

            override fun onPageFinished(view: WebView, url: String) {
                progressBar.visibility = View.GONE
            }

            override fun onReceivedError(
                view: WebView,
                request: WebResourceRequest,
                error: WebResourceError,
            ) {
                if (request.isForMainFrame) {
                    showError(error.description?.toString())
                }
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView, newProgress: Int) {
                progressBar.progress = newProgress
                progressBar.visibility =
                    if (newProgress in 1..99) View.VISIBLE else View.GONE
            }
        }

        webView.setDownloadListener { url, userAgent, contentDisposition, mimeType, _ ->
            onDownloadRequested(url, userAgent, contentDisposition, mimeType)
        }
    }

    /** Keeps same-origin navigation in the app; sends everything else out. */
    private fun handleUrl(uri: Uri): Boolean {
        val scheme = uri.scheme?.lowercase().orEmpty()
        if (scheme == "http" || scheme == "https") {
            val host = uri.host
            val serverHost = runCatching { Uri.parse(serverUrl).host }.getOrNull()
            if (host != null && serverHost != null && host.equals(serverHost, ignoreCase = true)) {
                return false
            }
        }
        if (scheme == "blob" || scheme == "data" || scheme == "javascript" || scheme == "about") {
            return false
        }
        openExternally(uri)
        return true
    }

    private fun openExternally(uri: Uri) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, uri))
        } catch (_: ActivityNotFoundException) {
            toast(getString(R.string.download_unsupported))
        }
    }

    // -------------------------------------------------------------- navigation

    private fun loadServer() {
        if (serverUrl.isBlank()) {
            showSetup()
            return
        }
        setupView.visibility = View.GONE
        errorView.visibility = View.GONE
        webView.visibility = View.VISIBLE
        progressBar.visibility = View.VISIBLE
        progressBar.progress = 0
        webView.loadUrl(serverUrl)
    }

    private fun showSetup() {
        webView.visibility = View.GONE
        errorView.visibility = View.GONE
        progressBar.visibility = View.GONE
        setupView.visibility = View.VISIBLE
        if (serverUrl.isNotBlank()) {
            serverInput.setText(serverUrl)
            serverInput.setSelection(serverInput.text.length)
        }
    }

    private fun showError(detail: String?) {
        progressBar.visibility = View.GONE
        webView.visibility = View.GONE
        setupView.visibility = View.GONE
        errorView.visibility = View.VISIBLE
        errorBody.text = if (detail.isNullOrBlank()) {
            getString(R.string.error_body)
        } else {
            getString(R.string.error_body) + "\n\n" + detail
        }
    }

    private fun connectToTypedServer() {
        val normalized = normalizeServerUrl(serverInput.text.toString())
        if (normalized == null) {
            toast(getString(R.string.setup_invalid))
            return
        }
        serverUrl = normalized
        prefs.edit().putString(KEY_SERVER, normalized).apply()
        loadServer()
    }

    /**
     * Accepts "host", "host:port" and full URLs. Bare LAN/loopback addresses
     * default to http:// because that is how a local Allin1 server is reached;
     * everything else defaults to https://.
     */
    private fun normalizeServerUrl(raw: String): String? {
        var value = raw.trim()
        if (value.isEmpty()) return null

        if (!value.startsWith("http://", ignoreCase = true) &&
            !value.startsWith("https://", ignoreCase = true)
        ) {
            val isLocal = Regex(
                "^(localhost|127\\.|10\\.|192\\.168\\.|172\\.(1[6-9]|2[0-9]|3[01])\\.)",
                RegexOption.IGNORE_CASE,
            ).containsMatchIn(value)
            value = if (isLocal) "http://$value" else "https://$value"
        }

        val uri = runCatching { Uri.parse(value) }.getOrNull() ?: return null
        if (uri.host.isNullOrBlank()) return null
        return value.trimEnd('/')
    }

    // --------------------------------------------------------------- downloads

    private fun onDownloadRequested(
        url: String,
        userAgent: String?,
        contentDisposition: String?,
        mimeType: String?,
    ) {
        val scheme = runCatching { Uri.parse(url).scheme?.lowercase() }.getOrNull()
        if (scheme != "http" && scheme != "https") {
            toast(getString(R.string.download_unsupported))
            return
        }

        val request = PendingDownload(url, userAgent, contentDisposition, mimeType)

        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q &&
            checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            pendingDownload = request
            requestPermissions(
                arrayOf(Manifest.permission.WRITE_EXTERNAL_STORAGE),
                REQ_STORAGE,
            )
            return
        }

        enqueueDownload(request)
    }

    private fun enqueueDownload(download: PendingDownload) {
        try {
            val fileName = URLUtil.guessFileName(
                download.url,
                download.contentDisposition,
                download.mimeType,
            )

            val request = DownloadManager.Request(Uri.parse(download.url))
                .setTitle(fileName)
                .setDescription(getString(R.string.download_description))
                .setNotificationVisibility(
                    DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED,
                )
                .setAllowedOverMetered(true)
                .setAllowedOverRoaming(true)
                .setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, fileName)

            download.mimeType?.takeIf { it.isNotBlank() }?.let { request.setMimeType(it) }
            download.userAgent?.takeIf { it.isNotBlank() }
                ?.let { request.addRequestHeader("User-Agent", it) }
            CookieManager.getInstance().getCookie(download.url)
                ?.let { request.addRequestHeader("Cookie", it) }

            val manager = getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
            manager.enqueue(request)
            toast(getString(R.string.download_started, fileName))
        } catch (_: Exception) {
            toast(getString(R.string.download_unsupported))
        }
    }

    @Suppress("DEPRECATION")
    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQ_STORAGE) return

        val queued = pendingDownload
        pendingDownload = null
        val granted = grantResults.isNotEmpty() &&
            grantResults[0] == PackageManager.PERMISSION_GRANTED
        when {
            queued == null -> Unit
            granted -> enqueueDownload(queued)
            else -> toast(getString(R.string.permission_needed))
        }
    }

    // -------------------------------------------------------------------- menu

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.menu_main, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean = when (item.itemId) {
        R.id.action_reload -> {
            loadServer(); true
        }
        R.id.action_change_server -> {
            showSetup(); true
        }
        R.id.action_open_browser -> {
            if (serverUrl.isNotBlank()) openExternally(Uri.parse(serverUrl))
            true
        }
        R.id.action_about -> {
            AlertDialog.Builder(this)
                .setTitle(R.string.about_title)
                .setMessage(R.string.about_body)
                .setPositiveButton(R.string.about_ok, null)
                .show()
            true
        }
        else -> super.onOptionsItemSelected(item)
    }

    // ----------------------------------------------------------------- state

    @Suppress("DEPRECATION", "OVERRIDE_DEPRECATION")
    override fun onBackPressed() {
        if (webView.visibility == View.VISIBLE && webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }

    override fun onDestroy() {
        webView.stopLoading()
        webView.setDownloadListener(null)
        webView.destroy()
        super.onDestroy()
    }

    private fun toast(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }

    private companion object {
        const val PREFS = "allin1_prefs"
        const val KEY_SERVER = "server_url"
        const val REQ_NOTIFICATIONS = 1001
        const val REQ_STORAGE = 1002
    }
}
