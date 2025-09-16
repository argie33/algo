import authService from './src/services/devAuth.js';

console.log('Available methods:', Object.getOwnPropertyNames(authService));
console.log('All keys:', Object.keys(authService));
console.log('signUp type:', typeof authService.signUp);
console.log('signUpWrapper type:', typeof authService.signUpWrapper);
console.log('validatePassword type:', typeof authService.validatePassword);
console.log('isAuthenticated type:', typeof authService.isAuthenticated);
console.log('getCurrentUserInfo type:', typeof authService.getCurrentUserInfo);
console.log('getJwtToken type:', typeof authService.getJwtToken);