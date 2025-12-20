/**
 * AWS Amplify Core Mock
 */

export const Hub = {
  listen: () => {},
  dispatch: () => {},
};

export const Cache = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
  clear: () => {},
};

export default {
  Hub,
  Cache,
};
