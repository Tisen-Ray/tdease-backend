const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("tdeaseDesktop", {
  platform: process.platform,
  runtime: "electron",
  openLogs: () => ipcRenderer.invoke("desktop:open-logs"),
});
