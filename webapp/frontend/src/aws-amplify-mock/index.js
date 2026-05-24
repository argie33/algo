/**
 * AWS Amplify Proxy - Delegates to real AWS Amplify library
 * This wrapper handles ES module compatibility issues while providing full functionality
 */

let realAmplify = null;

// Lazy-load the real Amplify library
async function getRealAmplify() {
  if (!realAmplify) {
    try {
      // Import real Amplify from node_modules
      const amplifyModule = await import('aws-amplify');
      realAmplify = amplifyModule.Amplify || amplifyModule.default || amplifyModule;
    } catch (error) {
      console.error('Failed to load real Amplify library:', error);
      // Return a safe fallback that doesn't break
      realAmplify = {
        configure: () => console.warn('Amplify not properly loaded'),
        getConfig: () => ({}),
      };
    }
  }
  return realAmplify;
}

// Proxy Amplify object that delegates to real implementation
export const Amplify = {
  configure: async (config) => {
    const amp = await getRealAmplify();
    return amp.configure ? amp.configure(config) : undefined;
  },
  getConfig: async () => {
    const amp = await getRealAmplify();
    return amp.getConfig ? amp.getConfig() : {};
  },
};

// Re-export auth functions
export * from './auth/index.js';

export default {
  Amplify,
};
