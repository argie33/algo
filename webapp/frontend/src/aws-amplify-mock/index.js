// Vitest mock for aws-amplify (replaces real package in test environment)
export const Amplify = {
  configure: () => {},
  getConfig: () => ({}),
};

export default Amplify;
