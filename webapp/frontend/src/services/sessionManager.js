// Session management utilities
let timeoutId = null;
let warningTimeoutId = null;
let callbacks = {};

export const sessionManager = {
  initialize: (config = {}) => {
    return true;
  },

  setCallbacks: (newCallbacks) => {
    callbacks = { ...callbacks, ...newCallbacks };
  },

  startSession: () => {
    clearTimeout(timeoutId);
    clearTimeout(warningTimeoutId);
  },

  endSession: () => {
    clearTimeout(timeoutId);
    clearTimeout(warningTimeoutId);
    if (callbacks.onSessionEnd) {
      callbacks.onSessionEnd();
    }
  },

  extendSession: () => {
    clearTimeout(timeoutId);
    clearTimeout(warningTimeoutId);
  },

  clearAllTimers: () => {
    clearTimeout(timeoutId);
    clearTimeout(warningTimeoutId);
  },
};

export default sessionManager;
