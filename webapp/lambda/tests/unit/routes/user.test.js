/**
 * User Routes Unit Tests  
 * Tests user 2FA functionality with database integration
 */

const express = require('express');
const request = require('supertest');

// Mock database
const mockQuery = jest.fn();
jest.mock('../../../utils/database', () => ({
  query: mockQuery
}));

// Mock speakeasy and qrcode
jest.mock('speakeasy', () => ({
  generateSecret: jest.fn(() => ({
    base32: 'JBSWY3DPEHPK3PXP',
    otpauth_url: 'otpauth://totp/FinancialPlatform%20(test%40example.com)?secret=JBSWY3DPEHPK3PXP&issuer=Financial%20Trading%20Platform'
  })),
  totp: {
    verify: jest.fn()
  }
}));

jest.mock('qrcode', () => ({
  toDataURL: jest.fn(() => Promise.resolve('data:image/png;base64,mockqrcode'))
}));

// Mock middleware
jest.mock('../../../middleware/responseFormatter', () => (req, res, next) => {
  res.success = (data) => res.json({ success: true, ...data });
  res.error = (message, statusCode = 500) => res.status(statusCode).json({ success: false, error: message });
  next();
});

const userRouter = require('../../../routes/user');

describe('User Routes - 2FA Functionality', () => {
  let app;
  
  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use('/user', userRouter);
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('POST /user/two-factor (enable)', () => {
    it('should enable 2FA and save secret to database', async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] }); // Mock successful insert

      const response = await request(app)
        .post('/user/two-factor')
        .send({
          action: 'enable',
          userId: 'test-user-123'
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.message).toContain('2FA setup initiated');
      expect(response.body.data).toHaveProperty('qrCode');
      expect(response.body.data).toHaveProperty('secret');
      expect(response.body.data).toHaveProperty('setupInstructions');
      
      // Verify database call was made
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('INSERT INTO user_2fa_secrets'),
        expect.arrayContaining(['test-user-123', 'JBSWY3DPEHPK3PXP'])
      );
    });

    it('should handle database errors gracefully during setup', async () => {
      mockQuery.mockRejectedValueOnce(new Error('Database connection failed'));

      const response = await request(app)
        .post('/user/two-factor')
        .send({
          action: 'enable',
          userId: 'test-user-123'
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.message).toContain('2FA setup initiated');
      // Should still return setup data even if DB save fails
      expect(response.body.data).toHaveProperty('qrCode');
    });
  });

  describe('POST /user/two-factor (verify)', () => {
    it('should verify 2FA code and activate', async () => {
      const speakeasy = require('speakeasy');
      
      mockQuery
        .mockResolvedValueOnce({ // SELECT secret
          rows: [{ secret: 'JBSWY3DPEHPK3PXP' }]
        })
        .mockResolvedValueOnce({ rows: [] }); // UPDATE is_active
      
      speakeasy.totp.verify.mockReturnValueOnce(true);

      const response = await request(app)
        .post('/user/two-factor')
        .send({
          action: 'verify',
          userId: 'test-user-123',
          code: '123456'
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.message).toContain('setup completed successfully');
      expect(response.body.data.activated).toBe(true);

      // Verify database calls
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('SELECT secret FROM user_2fa_secrets'),
        ['test-user-123']
      );
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('UPDATE user_2fa_secrets SET is_active = true'),
        ['test-user-123']
      );
    });

    it('should reject invalid 2FA codes', async () => {
      const speakeasy = require('speakeasy');
      
      mockQuery.mockResolvedValueOnce({
        rows: [{ secret: 'JBSWY3DPEHPK3PXP' }]
      });
      
      speakeasy.totp.verify.mockReturnValueOnce(false);

      const response = await request(app)
        .post('/user/two-factor')
        .send({
          action: 'verify',
          userId: 'test-user-123',
          code: 'invalid'
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Invalid 2FA code');
    });

    it('should handle missing 2FA setup', async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .post('/user/two-factor')
        .send({
          action: 'verify',
          userId: 'test-user-123',
          code: '123456'
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('No 2FA setup found');
    });
  });

  describe('POST /user/two-factor (disable)', () => {
    it('should disable 2FA after verifying current code', async () => {
      const speakeasy = require('speakeasy');
      
      mockQuery
        .mockResolvedValueOnce({ // SELECT secret
          rows: [{ secret: 'JBSWY3DPEHPK3PXP' }]
        })
        .mockResolvedValueOnce({ rows: [] }); // DELETE
      
      speakeasy.totp.verify.mockReturnValueOnce(true);

      const response = await request(app)
        .post('/user/two-factor')
        .send({
          action: 'disable',
          userId: 'test-user-123',
          code: '123456'
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.message).toContain('disabled successfully');

      // Verify database calls
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('SELECT secret FROM user_2fa_secrets'),
        ['test-user-123']
      );
      expect(mockQuery).toHaveBeenCalledWith(
        'DELETE FROM user_2fa_secrets WHERE user_id = $1',
        ['test-user-123']
      );
    });

    it('should require valid code to disable', async () => {
      const speakeasy = require('speakeasy');
      
      mockQuery.mockResolvedValueOnce({
        rows: [{ secret: 'JBSWY3DPEHPK3PXP' }]
      });
      
      speakeasy.totp.verify.mockReturnValueOnce(false);

      const response = await request(app)
        .post('/user/two-factor')
        .send({
          action: 'disable',
          userId: 'test-user-123',
          code: 'invalid'
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Invalid 2FA code');
    });
  });

  describe('Error handling', () => {
    it('should require action parameter', async () => {
      const response = await request(app)
        .post('/user/two-factor')
        .send({
          userId: 'test-user-123'
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Missing required parameters');
    });

    it('should require userId parameter', async () => {
      const response = await request(app)
        .post('/user/two-factor')
        .send({
          action: 'enable'
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Missing required parameters');
    });

    it('should handle invalid actions', async () => {
      const response = await request(app)
        .post('/user/two-factor')
        .send({
          action: 'invalid',
          userId: 'test-user-123'
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Invalid action');
    });
  });
});