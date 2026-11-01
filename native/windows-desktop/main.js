const { app, BrowserWindow, shell } = require('electron');
const path = require('path');
const APP_URL = 'https://my-ai-pro-rkxe.onrender.com';

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.whenReady().then(() => {
    const win = new BrowserWindow({
      width: 1360,
      height: 900,
      minWidth: 900,
      minHeight: 600,
      backgroundColor: '#0A0E1A',
      autoHideMenuBar: true,
      title: 'Smash AI Pro',
      icon: path.join(__dirname, 'build', 'icon.png'),
      webPreferences: { contextIsolation: true, nodeIntegration: false }
    });
    win.loadURL(APP_URL).catch(() => win.loadFile('offline.html'));
    win.webContents.setWindowOpenHandler(({ url }) => {
      if (!url.includes('onrender.com')) shell.openExternal(url);
      return { action: 'deny' };
    });
  });
  app.on('window-all-closed', () => app.quit());
}
