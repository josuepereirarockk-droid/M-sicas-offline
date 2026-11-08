#!/usr/bin/env python3
"""Gera o projeto Android (WebView + serviço de reprodução em segundo plano)
a partir dos arquivos do app. Rodado automaticamente pelo GitHub Actions."""
import os, shutil, sys

WEB = ['index.html', 'sw.js', 'manifest.json', 'tags.js', 'tags-worker.js', 'icon.svg', 'icon-192.png',
       'icon-512.png', 'icon-maskable-512.png', 'apple-touch-icon.png', 'bg-butterfly.jpg', 'bg-city-top.jpg', 'bg-city-char.jpg']
PKG = 'br.musicas.offline'
ROOT = 'android'

FILES = {}
FILES['settings.gradle'] = """pluginManagement {
    repositories { google(); mavenCentral(); gradlePluginPortal() }
}
dependencyResolutionManagement {
    repositories { google(); mavenCentral() }
}
rootProject.name = 'Musicas'
include ':app'
"""
FILES['build.gradle'] = """plugins {
    id 'com.android.application' version '8.5.2' apply false
}
"""
FILES['gradle.properties'] = """org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8
android.nonTransitiveRClass=true
"""
FILES['app/build.gradle'] = """plugins {
    id 'com.android.application'
}
android {
    namespace 'br.musicas.offline'
    compileSdk 34
    defaultConfig {
        applicationId 'br.musicas.offline'
        minSdk 24
        targetSdk 34
        versionCode 1
        versionName '1.0'
    }
    buildTypes {
        release { minifyEnabled false }
    }
    compileOptions {
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }
}
"""
FILES['app/src/main/AndroidManifest.xml'] = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK" />
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
    <uses-permission android:name="android.permission.WAKE_LOCK" />
    <uses-permission android:name="android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS" />

    <application
        android:label="Músicas"
        android:icon="@mipmap/ic_launcher"
        android:allowBackup="true"
        android:theme="@style/AppTheme">

        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:launchMode="singleTask"
            android:configChanges="orientation|screenSize|keyboardHidden|smallestScreenSize|screenLayout|uiMode">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>

        <service
            android:name=".PlaybackService"
            android:exported="false"
            android:foregroundServiceType="mediaPlayback" />
    </application>
</manifest>
"""
FILES['app/src/main/res/values/styles.xml'] = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="AppTheme" parent="android:Theme.DeviceDefault.NoActionBar">
        <item name="android:windowBackground">@android:color/black</item>
        <item name="android:statusBarColor">#05050F</item>
        <item name="android:navigationBarColor">#05050F</item>
    </style>
</resources>
"""
FILES['app/src/main/java/br/musicas/offline/MainActivity.java'] = r'''package br.musicas.offline;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.HashMap;

public class MainActivity extends Activity {
    static MainActivity current;
    static final String HOST = "appassets.androidplatform.net";
    static final int REQ_FILES = 1;
    static final int REQ_NOTIF = 2;

    WebView web;
    ValueCallback<Uri[]> chooser;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        current = this;
        web = new WebView(this);
        web.setBackgroundColor(0xFF05050F);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(false);
        s.setSupportZoom(false);

        web.addJavascriptInterface(new Bridge(), "AndroidBridge");

        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                Uri u = request.getUrl();
                if (!HOST.equals(u.getHost())) return null;
                String p = u.getPath();
                if (p == null || p.isEmpty() || p.equals("/")) p = "/index.html";
                try {
                    InputStream in = getAssets().open("www" + p);
                    String m = mime(p);
                    boolean text = m.startsWith("text/") || m.equals("application/json") || m.equals("image/svg+xml");
                    return new WebResourceResponse(m, text ? "utf-8" : null, in);
                } catch (IOException e) {
                    return new WebResourceResponse("text/plain", "utf-8", 404, "Not Found",
                            new HashMap<String, String>(), new ByteArrayInputStream(new byte[0]));
                }
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                if (HOST.equals(request.getUrl().getHost())) return false;
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, request.getUrl()));
                } catch (Exception ignored) {
                }
                return true;
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView w, ValueCallback<Uri[]> cb, FileChooserParams params) {
                if (chooser != null) chooser.onReceiveValue(null);
                chooser = cb;
                try {
                    startActivityForResult(params.createIntent(), REQ_FILES);
                } catch (Exception e) {
                    chooser = null;
                    return false;
                }
                return true;
            }
        });

        web.loadUrl("https://" + HOST + "/index.html");
        askPermissions();
    }

    static String mime(String p) {
        String q = p.toLowerCase();
        if (q.endsWith(".html")) return "text/html";
        if (q.endsWith(".js")) return "text/javascript";
        if (q.endsWith(".json")) return "application/json";
        if (q.endsWith(".css")) return "text/css";
        if (q.endsWith(".png")) return "image/png";
        if (q.endsWith(".jpg") || q.endsWith(".jpeg")) return "image/jpeg";
        if (q.endsWith(".svg")) return "image/svg+xml";
        return "application/octet-stream";
    }

    void askPermissions() {
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission("android.permission.POST_NOTIFICATIONS") != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, REQ_NOTIF);
        }
        final SharedPreferences sp = getSharedPreferences("musicas", MODE_PRIVATE);
        if (!sp.getBoolean("bateria", false) && Build.VERSION.SDK_INT >= 23) {
            PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
            if (pm != null && !pm.isIgnoringBatteryOptimizations(getPackageName())) {
                new AlertDialog.Builder(this)
                        .setTitle("Tocar em segundo plano")
                        .setMessage("Para a música continuar tocando com a tela apagada, permita que o app rode sem restrição de bateria na próxima tela.")
                        .setPositiveButton("Continuar", new DialogInterface.OnClickListener() {
                            @Override
                            public void onClick(DialogInterface d, int w) {
                                sp.edit().putBoolean("bateria", true).apply();
                                try {
                                    startActivity(new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                                            Uri.parse("package:" + getPackageName())));
                                } catch (Exception e) {
                                    try {
                                        startActivity(new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS));
                                    } catch (Exception ignored) {
                                    }
                                }
                            }
                        })
                        .setNegativeButton("Agora não", null)
                        .show();
            }
        }
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        if (req == REQ_FILES && chooser != null) {
            Uri[] r = null;
            if (res == RESULT_OK) r = WebChromeClient.FileChooserParams.parseResult(res, data);
            chooser.onReceiveValue(r);
            chooser = null;
            return;
        }
        super.onActivityResult(req, res, data);
    }

    /** Voltar: o app fecha o que estiver aberto; se não houver nada, vai para o fundo e a música continua. */
    @Override
    public void onBackPressed() {
        web.evaluateJavascript(
                "(function(){try{return window.nativeBack?window.nativeBack():false}catch(e){return false}})()",
                new ValueCallback<String>() {
                    @Override
                    public void onReceiveValue(String v) {
                        if (!"true".equals(v)) moveTaskToBack(true);
                    }
                });
    }

    @Override
    protected void onDestroy() {
        if (current == this) current = null;
        if (isFinishing()) stopService(new Intent(this, PlaybackService.class));
        super.onDestroy();
    }

    /** Chamada pelo JavaScript do app. */
    class Bridge {
        @JavascriptInterface
        public void state(boolean playing, String title, String artist) {
            PlaybackService svc = PlaybackService.inst;
            if (svc != null) {
                svc.postUpdate(playing, title, artist);
                return;
            }
            if (!playing) return;
            Intent i = new Intent(MainActivity.this, PlaybackService.class);
            i.putExtra("playing", true).putExtra("title", title).putExtra("artist", artist);
            try {
                if (Build.VERSION.SDK_INT >= 26) startForegroundService(i);
                else startService(i);
            } catch (Exception ignored) {
            }
        }
    }
}
'''
FILES['app/src/main/java/br/musicas/offline/PlaybackService.java'] = r'''package br.musicas.offline;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.drawable.Icon;
import android.media.MediaMetadata;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;

/** Mantém o app vivo em segundo plano (serviço de primeiro plano) e mostra os controles na notificação. */
public class PlaybackService extends Service {
    static PlaybackService inst;
    static final String CHANNEL = "musicas_reproducao";
    static final int NOTIF_ID = 7;

    MediaSession session;
    PowerManager.WakeLock wl;
    boolean playing = false;
    boolean fg = false;
    String title = "Músicas";
    String artist = "";

    @Override
    public void onCreate() {
        super.onCreate();
        inst = this;
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel ch = new NotificationChannel(CHANNEL, "Reprodução", NotificationManager.IMPORTANCE_LOW);
            ch.setShowBadge(false);
            getSystemService(NotificationManager.class).createNotificationChannel(ch);
        }
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        wl = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "musicas:reproducao");
        wl.setReferenceCounted(false);

        session = new MediaSession(this, "Musicas");
        session.setFlags(MediaSession.FLAG_HANDLES_MEDIA_BUTTONS | MediaSession.FLAG_HANDLES_TRANSPORT_CONTROLS);
        session.setCallback(new MediaSession.Callback() {
            @Override public void onPlay() { cmd("play"); }
            @Override public void onPause() { cmd("pause"); }
            @Override public void onSkipToNext() { cmd("next"); }
            @Override public void onSkipToPrevious() { cmd("prev"); }
        });
        session.setActive(true);
    }

    @Override
    public int onStartCommand(Intent i, int flags, int startId) {
        if (i != null && "cmd".equals(i.getAction())) {
            if (!fg) {
                stopSelf();
                return START_NOT_STICKY;
            }
            cmd(i.getStringExtra("c"));
            return START_NOT_STICKY;
        }
        boolean p = i != null && i.getBooleanExtra("playing", false);
        String t = i == null ? null : i.getStringExtra("title");
        String a = i == null ? null : i.getStringExtra("artist");
        applyState(p, t, a);
        Notification n = buildNotification();
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
        } else {
            startForeground(NOTIF_ID, n);
        }
        fg = true;
        return START_NOT_STICKY;
    }

    void postUpdate(final boolean p, final String t, final String a) {
        new Handler(Looper.getMainLooper()).post(new Runnable() {
            @Override
            public void run() {
                applyState(p, t, a);
                NotificationManager nm = getSystemService(NotificationManager.class);
                nm.notify(NOTIF_ID, buildNotification());
            }
        });
    }

    void applyState(boolean p, String t, String a) {
        playing = p;
        if (t != null && !t.isEmpty()) title = t;
        artist = a == null ? "" : a;
        session.setMetadata(new MediaMetadata.Builder()
                .putString(MediaMetadata.METADATA_KEY_TITLE, title)
                .putString(MediaMetadata.METADATA_KEY_ARTIST, artist)
                .build());
        long actions = PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE | PlaybackState.ACTION_PLAY_PAUSE
                | PlaybackState.ACTION_SKIP_TO_NEXT | PlaybackState.ACTION_SKIP_TO_PREVIOUS;
        session.setPlaybackState(new PlaybackState.Builder()
                .setActions(actions)
                .setState(p ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED,
                        PlaybackState.PLAYBACK_POSITION_UNKNOWN, 1f)
                .build());
        if (p && !wl.isHeld()) wl.acquire(4 * 60 * 60 * 1000L);
        else if (!p && wl.isHeld()) wl.release();
    }

    Notification buildNotification() {
        Notification.Builder b = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CHANNEL)
                : new Notification.Builder(this);
        PendingIntent open = PendingIntent.getActivity(this, 0,
                new Intent(this, MainActivity.class).setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        b.setSmallIcon(android.R.drawable.ic_media_play)
                .setContentTitle(title)
                .setContentText(artist)
                .setOngoing(playing)
                .setShowWhen(false)
                .setVisibility(Notification.VISIBILITY_PUBLIC)
                .setContentIntent(open)
                .addAction(new Notification.Action.Builder(
                        Icon.createWithResource(this, android.R.drawable.ic_media_previous), "Anterior", pi("prev", 1)).build())
                .addAction(new Notification.Action.Builder(
                        Icon.createWithResource(this, playing ? android.R.drawable.ic_media_pause : android.R.drawable.ic_media_play),
                        playing ? "Pausar" : "Tocar", pi(playing ? "pause" : "play", 2)).build())
                .addAction(new Notification.Action.Builder(
                        Icon.createWithResource(this, android.R.drawable.ic_media_next), "Próxima", pi("next", 3)).build())
                .setStyle(new Notification.MediaStyle()
                        .setMediaSession(session.getSessionToken())
                        .setShowActionsInCompactView(0, 1, 2));
        return b.build();
    }

    PendingIntent pi(String c, int code) {
        Intent i = new Intent(this, PlaybackService.class).setAction("cmd").putExtra("c", c);
        return PendingIntent.getService(this, code, i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    void cmd(String c) {
        if (c == null) return;
        final MainActivity act = MainActivity.current;
        if (act == null || act.web == null) return;
        final String js = "window.nativeCmd&&nativeCmd('" + c + "')";
        act.web.post(new Runnable() {
            @Override
            public void run() {
                act.web.evaluateJavascript(js, null);
            }
        });
    }

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        stopSelf();
        super.onTaskRemoved(rootIntent);
    }

    @Override
    public void onDestroy() {
        inst = null;
        fg = false;
        try { if (wl != null && wl.isHeld()) wl.release(); } catch (Exception ignored) { }
        try { session.release(); } catch (Exception ignored) { }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
'''

def main():
    for f in WEB:
        if not os.path.exists(f):
            sys.exit('Arquivo do app não encontrado: ' + f)
    shutil.rmtree(ROOT, ignore_errors=True)
    for path, content in FILES.items():
        full = os.path.join(ROOT, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w', encoding='utf-8') as fh:
            fh.write(content)
    www = os.path.join(ROOT, 'app/src/main/assets/www')
    os.makedirs(www, exist_ok=True)
    for f in WEB:
        shutil.copy(f, os.path.join(www, f))
    for d in ('mdpi', 'hdpi', 'xhdpi', 'xxhdpi', 'xxxhdpi'):
        out = os.path.join(ROOT, 'app/src/main/res/mipmap-' + d)
        os.makedirs(out, exist_ok=True)
        shutil.copy('icon-192.png', os.path.join(out, 'ic_launcher.png'))
    print('Projeto Android gerado em', ROOT)

if __name__ == '__main__':
    main()
