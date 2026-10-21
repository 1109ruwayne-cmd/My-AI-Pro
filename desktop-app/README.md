# My AI Pro Desktop (Windows)

Electron shell around the hosted My AI Pro service - a standalone Windows app:
own window, tray icon, closes-to-tray, single instance, external links open in the
default browser. NO secrets are embedded: brain, keys and billing stay server-side.

- Run locally (Linux/mac dev): `npm install && npm start`
- Build Windows package: `npm run dist` (NSIS installer needs wine on Linux; the
  portable `dist/win-unpacked` folder builds everywhere and is what v1.0.0 ships:
  zip it, user unzips and runs "My AI Pro.exe").
- Release asset lives on GitHub Releases (tag v1.0.0-desktop); sha256 in ../releases/README.md.
- Code-signing: when a Windows machine + cert are available, build there for a
  signed NSIS installer (no SmartScreen warning).
