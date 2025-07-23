/**
 * Browser API Mocks
 * Applied before any service imports to prevent constructor errors
 */

// Mock AudioContext at global level
global.AudioContext = class MockAudioContext {
  constructor() {
    this.destination = {};
    this.sampleRate = 44100;
    this.currentTime = 0;
    this.state = 'running';
  }
  createOscillator() {
    return {
      frequency: { value: 440 },
      connect: () => {},
      start: () => {},
      stop: () => {}
    };
  }
  createGain() {
    return {
      gain: { value: 1 },
      connect: () => {}
    };
  }
  close() { return Promise.resolve(); }
};

global.webkitAudioContext = global.AudioContext;

// Mock Notification at global level
global.Notification = class MockNotification {
  constructor(title, options) {
    this.title = title;
    this.body = options?.body;
    this.icon = options?.icon;
  }
  static requestPermission() {
    return Promise.resolve('granted');
  }
  static permission = 'granted';
};

// Ensure these are available on window as well
if (typeof window !== 'undefined') {
  window.AudioContext = global.AudioContext;
  window.webkitAudioContext = global.webkitAudioContext; 
  window.Notification = global.Notification;
}