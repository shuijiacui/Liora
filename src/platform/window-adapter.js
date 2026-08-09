const DESKTOP_COMPACT_SIZE = Object.freeze({ width: 420, height: 410 });
const DESKTOP_DIALOG_SIZE = Object.freeze({ width: 650, height: 430 });
const DEVICE_PREVIEW_SIZE = Object.freeze({ width: 800, height: 480 });
const EDGE_MARGIN = Object.freeze({ right: 20, bottom: 8 });

class DesktopWindowAdapter {
  constructor({ BrowserWindow, Notification, screen, preloadPath, indexPath }) {
    this.BrowserWindow = BrowserWindow;
    this.Notification = Notification;
    this.screen = screen;
    this.preloadPath = preloadPath;
    this.indexPath = indexPath;
    this.windowMode = 'compact';
  }

  currentSize() {
    return this.windowMode === 'dialog' ? DESKTOP_DIALOG_SIZE : DESKTOP_COMPACT_SIZE;
  }

  clampToWorkArea(position, size = this.currentSize()) {
    const display = this.screen.getDisplayNearestPoint(position);
    const area = display.workArea;
    return {
      x: Math.min(Math.max(position.x, area.x), area.x + area.width - size.width),
      y: Math.min(Math.max(position.y, area.y), area.y + area.height - size.height)
    };
  }

  defaultDockPosition(size = this.currentSize()) {
    const area = this.screen.getPrimaryDisplay().workArea;
    return {
      x: area.x + area.width - size.width - EDGE_MARGIN.right,
      y: area.y + area.height - size.height - EDGE_MARGIN.bottom
    };
  }

  createWindow(savedPosition) {
    const position = savedPosition
      ? this.clampToWorkArea(savedPosition, DESKTOP_COMPACT_SIZE)
      : this.defaultDockPosition(DESKTOP_COMPACT_SIZE);
    const window = new this.BrowserWindow({
      ...DESKTOP_COMPACT_SIZE,
      ...position,
      frame: false,
      useContentSize: true,
      transparent: true,
      backgroundColor: '#00000000',
      hasShadow: false,
      resizable: false,
      minWidth: DESKTOP_COMPACT_SIZE.width,
      minHeight: DESKTOP_COMPACT_SIZE.height,
      maxWidth: DESKTOP_DIALOG_SIZE.width,
      maxHeight: DESKTOP_DIALOG_SIZE.height,
      maximizable: false,
      minimizable: false,
      fullscreenable: false,
      movable: true,
      focusable: false,
      show: false,
      alwaysOnTop: true,
      skipTaskbar: true,
      webPreferences: {
        preload: this.preloadPath,
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true
      }
    });
    window.setAlwaysOnTop(true, 'floating');
    window.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: false });
    window.loadFile(this.indexPath);
    return window;
  }

  setWindowMode(window, mode) {
    if (!window || window.isDestroyed() || mode === this.windowMode) return;
    const bounds = window.getBounds();
    const nextSize = mode === 'dialog' ? DESKTOP_DIALOG_SIZE : DESKTOP_COMPACT_SIZE;
    const nextPosition = this.clampToWorkArea({
      x: bounds.x + bounds.width - nextSize.width,
      y: bounds.y + bounds.height - nextSize.height
    }, nextSize);

    this.windowMode = mode;
    window.setBounds({ ...nextPosition, ...nextSize }, true);
    window.setFocusable(mode === 'dialog');
    this.showWindow(window);
  }

  showWindow(window) {
    if (!window || window.isDestroyed()) return;
    if (window.isMinimized()) window.restore();
    if (this.windowMode === 'dialog') {
      window.show();
      window.focus();
    } else {
      window.showInactive();
    }
    window.moveTop();
  }

  hideWindow(window) {
    window?.hide();
  }

  dockWindow(window) {
    if (!window || window.isDestroyed()) return;
    const size = this.currentSize();
    window.setBounds({ ...this.defaultDockPosition(size), ...size }, true);
  }

  savedPosition(window) {
    if (!window || window.isDestroyed()) return null;
    const bounds = window.getBounds();
    return {
      x: bounds.x + bounds.width - DESKTOP_COMPACT_SIZE.width,
      y: bounds.y + bounds.height - DESKTOP_COMPACT_SIZE.height
    };
  }

  presentReminder(window, payload, onActivate) {
    if (!this.Notification.isSupported()) return;
    const notification = new this.Notification({ ...payload, silent: true });
    notification.on('click', onActivate);
    notification.show();
  }
}

class DeviceWindowAdapter {
  constructor({ BrowserWindow, screen, preloadPath, indexPath, windowed }) {
    this.BrowserWindow = BrowserWindow;
    this.screen = screen;
    this.preloadPath = preloadPath;
    this.indexPath = indexPath;
    this.windowed = windowed;
    this.windowMode = 'compact';
  }

  createWindow() {
    const display = this.screen.getPrimaryDisplay();
    const bounds = display.bounds;
    const size = this.windowed ? DEVICE_PREVIEW_SIZE : { width: bounds.width, height: bounds.height };
    const position = this.windowed
      ? {
          x: bounds.x + Math.round((bounds.width - size.width) / 2),
          y: bounds.y + Math.round((bounds.height - size.height) / 2)
        }
      : { x: bounds.x, y: bounds.y };
    const window = new this.BrowserWindow({
      ...size,
      ...position,
      frame: false,
      useContentSize: true,
      transparent: false,
      backgroundColor: '#f5ead7',
      resizable: this.windowed,
      fullscreenable: true,
      kiosk: !this.windowed,
      fullscreen: !this.windowed,
      show: false,
      autoHideMenuBar: true,
      webPreferences: {
        preload: this.preloadPath,
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true
      }
    });
    window.loadFile(this.indexPath);
    return window;
  }

  setWindowMode(window, mode) {
    this.windowMode = mode;
    this.showWindow(window);
  }

  showWindow(window) {
    if (!window || window.isDestroyed()) return;
    if (window.isMinimized()) window.restore();
    window.show();
    window.focus();
  }

  hideWindow() {
    // A dedicated device has no tray to recover a hidden window from.
  }

  dockWindow() {}

  savedPosition() {
    return null;
  }

  presentReminder(window, payload) {
    this.showWindow(window);
    window?.webContents.send('reminder:show', payload);
  }
}

function createWindowAdapter({ profile, ...dependencies }) {
  if (profile.mode === 'device') {
    return new DeviceWindowAdapter({ ...dependencies, windowed: profile.deviceWindowed });
  }
  return new DesktopWindowAdapter(dependencies);
}

module.exports = {
  DESKTOP_COMPACT_SIZE,
  DESKTOP_DIALOG_SIZE,
  DEVICE_PREVIEW_SIZE,
  createWindowAdapter
};
