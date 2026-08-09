const test = require('node:test');
const assert = require('node:assert/strict');
const { createWindowAdapter } = require('../src/platform/window-adapter');

class MockWindow {
  constructor(options) {
    this.options = options;
    this.bounds = { x: options.x, y: options.y, width: options.width, height: options.height };
    this.focusable = options.focusable;
    this.loadedFile = '';
  }

  setAlwaysOnTop() {}
  setVisibleOnAllWorkspaces() {}
  loadFile(value) { this.loadedFile = value; }
  isDestroyed() { return false; }
  isMinimized() { return false; }
  getBounds() { return this.bounds; }
  setBounds(value) { this.bounds = value; }
  setFocusable(value) { this.focusable = value; }
  show() { this.visible = true; }
  showInactive() { this.visible = true; }
  focus() { this.focused = true; }
  moveTop() {}
  hide() { this.visible = false; }
}

const screen = {
  getPrimaryDisplay: () => ({
    bounds: { x: 0, y: 0, width: 1920, height: 1080 },
    workArea: { x: 0, y: 0, width: 1920, height: 1040 }
  }),
  getDisplayNearestPoint: () => ({ workArea: { x: 0, y: 0, width: 1920, height: 1040 } })
};

test('desktop adapter creates a transparent docked window and resizes around its anchor', () => {
  const adapter = createWindowAdapter({
    profile: { mode: 'desktop' },
    BrowserWindow: MockWindow,
    Notification: { isSupported: () => false },
    screen,
    preloadPath: 'preload.js',
    indexPath: 'index.html'
  });
  const window = adapter.createWindow();
  assert.equal(window.options.transparent, true);
  assert.equal(window.bounds.width, 420);
  adapter.setWindowMode(window, 'dialog');
  assert.equal(window.bounds.width, 650);
  assert.equal(window.bounds.height, 430);
  assert.equal(window.focusable, true);
});

test('device adapter creates an opaque 800x480 preview without kiosk lock', () => {
  const adapter = createWindowAdapter({
    profile: { mode: 'device', deviceWindowed: true },
    BrowserWindow: MockWindow,
    Notification: { isSupported: () => false },
    screen,
    preloadPath: 'preload.js',
    indexPath: 'index.html'
  });
  const window = adapter.createWindow();
  assert.equal(window.options.transparent, false);
  assert.equal(window.options.width, 800);
  assert.equal(window.options.height, 480);
  assert.equal(window.options.kiosk, false);
  assert.equal(adapter.savedPosition(window), null);
});
