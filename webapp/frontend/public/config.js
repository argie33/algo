// Runtime configuration - dynamically set during deployment
window.__CONFIG__ = {
  API_URL: 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev',
  ENVIRONMENT: 'dev',
  VERSION: '20250711-011431',
  BUILD_TIME: '2025-07-11T01:14:31Z',
  COGNITO: {
    USER_POOL_ID: 'us-east-1_ZqooNeQtV',
    CLIENT_ID: '243r98prucoickch12djkahrhk',
    REGION: 'us-east-1',
    DOMAIN: '',
    REDIRECT_SIGN_IN: 'https://d1zb7knau41vl9.cloudfront.net',
    REDIRECT_SIGN_OUT: 'https://d1zb7knau41vl9.cloudfront.net'
  }
};
console.log('Runtime config loaded:', window.__CONFIG__);
