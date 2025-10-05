/**
 * AWS Amplify Mock - Root export
 */

// Mock Amplify object
export const Amplify = {
  configure: () => {},
  getConfig: () => ({}),
};

// Re-export auth functions
export * from './auth/index.js';

export default {
  Amplify,
};
