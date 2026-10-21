// My AI Pro - Windows desktop shell.
// A standalone native window around the hosted My AI Pro service.
// No secrets live here: the AI brain, keys and billing stay on the server.
const { app, BrowserWindow, Menu, Tray, shell, dialog } = require('electron');
const path = require('path');

const APP_URL = 'https://my-ai-pro-rkxe.onrender.com';
const APP_HOST = 'my-ai-pro-rkxe.onrender.com';

// One instance only - a second launch just focuses the running window.
if (!app.requestSingleInstanceLock()) { app.quit(); }

let win = null;
let tray = null;

function retryPage(detail) {
  return 'data:text/html;charset=utf-8,' + encodeURIComponent(
    '<body style="font-family:Segoe UI,system-ui,sans-serif;background:#12122a;color:#eee;' +
    'display:flex;align-items:center;justify-content:center;height:100vh;margin:0">' +
    '<div style="text-align:center;max-width:420px"><h2 style="margin:0 0 8px">📡 My AI Pro is reaching the server…</h2>' +
    '<p style="color:#aab;margin:0 0 18px">No connection yet. Check your internet, then try again.' +
    (detail ? '<br><small style="color:#778">' + String(detail).replace(/[<>&]/g, '') + '</small>' : '') + '</p>' +
    '<button onclick="location.reload()" style="padding:10px 26px;border:0;border-radius:10px;background:#6c5ce7;' +
    'color:#fff;font-size:15px;cursor:pointer">Retry</button></div></body>');
}

function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 900,
    minHeight: 600,
    title: 'My AI Pro',
    icon: path.join(__dirname, 'assets', 'icon.png'),
    backgroundColor: '#12122a',
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  // Anything that is not My AI Pro opens in the user's real browser.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith(APP_URL)) shell.openExternal(url);
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (e, url) => {
    let host = '';
    try { host = new URL(url).host; } catch (err) { return; }
    if (host !== APP_HOST) { e.preventDefault(); shell.openExternal(url); }
  });

  win.webContents.on('did-fail-load', (_e, code, desc) => {
    win.loadURL(retryPage(code + ' ' + desc));
  });

  win.loadURL(APP_URL);

  win.on('close', (e) => {
    // Close hides to tray - the app keeps running "separate on Windows".
    if (!app.isQuitting) { e.preventDefault(); win.hide(); }
  });
}

function createTray() {
  tray = new Tray(path.join(__dirname, 'assets', 'icon.png'));
  tray.setToolTip('My AI Pro');
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Open My AI Pro', click: () => { win.show(); win.focus(); } },
    { label: 'Reload', click: () => { win.show(); win.loadURL(APP_URL); } },
    { type: 'separator' },
    { label: 'Quit', click: () => { app.isQuitting = true; app.quit(); } },
  ]));
  tray.on('double-click', () => { win.show(); win.focus(); });
}

app.whenReady().then(() => {
  createWindow();
  createTray();
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { label: 'App', submenu: [
      { label: 'Reload', accelerator: 'CmdOrCtrl+R', click: () => win.loadURL(APP_URL) },
      { label: 'Zoom In', accelerator: 'CmdOrCtrl+Plus', click: () => win.webContents.setZoomLevel(win.webContents.getZoomLevel() + 1) },
      { label: 'Zoom Out', accelerator: 'CmdOrCtrl+-', click: () => win.webContents.setZoomLevel(win.webContents.getZoomLevel() - 1) },
      { type: 'separator' },
      { label: 'Quit', accelerator: 'CmdOrCtrl+Q', click: () => { app.isQuitting = true; app.quit(); } },
    ] },
  ]));
});

app.on('second-instance', () => { if (win) { win.show(); win.focus(); } });
app.on('window-all-closed', () => { /* keep living in the tray */ });
app.on('before-quit', () => { app.isQuitting = true; });
