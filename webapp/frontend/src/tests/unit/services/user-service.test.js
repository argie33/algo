/**
 * User Service Unit Tests
 * Comprehensive testing of user management and profile operations
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock external dependencies
vi.mock('../../../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  patch: vi.fn()
}));

vi.mock('../../../services/storage', () => ({
  setItem: vi.fn(),
  getItem: vi.fn(),
  removeItem: vi.fn()
}));

// Mock User Service
class UserService {
  constructor(apiClient, storage) {
    this.api = apiClient;
    this.storage = storage;
    this.userCacheKey = 'cached_user_data';
    this.preferencesCacheKey = 'user_preferences';
  }

  async getUserProfile(userId) {
    if (!userId) {
      throw new Error('User ID is required');
    }

    try {
      const response = await this.api.get(`/users/${userId}/profile`);
      const profile = this.processUserProfile(response);
      
      // Cache the profile
      this.storage.setItem(this.userCacheKey, JSON.stringify(profile));
      
      return profile;
    } catch (error) {
      throw this.handleUserError(error);
    }
  }

  async updateUserProfile(userId, profileData) {
    if (!userId) {
      throw new Error('User ID is required');
    }

    this.validateProfileData(profileData);

    try {
      const response = await this.api.put(`/users/${userId}/profile`, profileData);
      const updatedProfile = this.processUserProfile(response);
      
      // Update cache
      this.storage.setItem(this.userCacheKey, JSON.stringify(updatedProfile));
      
      return updatedProfile;
    } catch (error) {
      throw this.handleUserError(error);
    }
  }

  async uploadProfilePicture(userId, file) {
    if (!userId) {
      throw new Error('User ID is required');
    }

    if (!file || !this.isValidImageFile(file)) {
      throw new Error('Valid image file is required');
    }

    const formData = new FormData();
    formData.append('profilePicture', file);

    try {
      const response = await this.api.post(`/users/${userId}/profile-picture`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });

      return {
        success: true,
        imageUrl: response.imageUrl,
        message: 'Profile picture updated successfully'
      };
    } catch (error) {
      throw this.handleUserError(error);
    }
  }

  async getUserPreferences(userId) {
    if (!userId) {
      throw new Error('User ID is required');
    }

    try {
      // Check cache first
      const cached = this.storage.getItem(this.preferencesCacheKey);
      if (cached) {
        const preferences = JSON.parse(cached);
        if (preferences.userId === userId) {
          return preferences;
        }
      }

      const response = await this.api.get(`/users/${userId}/preferences`);
      const preferences = this.processUserPreferences(response, userId);
      
      // Cache preferences
      this.storage.setItem(this.preferencesCacheKey, JSON.stringify(preferences));
      
      return preferences;
    } catch (error) {
      throw this.handleUserError(error);
    }
  }

  async updateUserPreferences(userId, preferences) {
    if (!userId) {
      throw new Error('User ID is required');
    }

    this.validatePreferences(preferences);

    try {
      const response = await this.api.put(`/users/${userId}/preferences`, preferences);
      const updatedPreferences = this.processUserPreferences(response, userId);
      
      // Update cache
      this.storage.setItem(this.preferencesCacheKey, JSON.stringify(updatedPreferences));
      
      return updatedPreferences;
    } catch (error) {
      throw this.handleUserError(error);
    }
  }

  async getUserNotifications(userId, options = {}) {
    if (!userId) {
      throw new Error('User ID is required');
    }

    const { page = 1, limit = 20, unreadOnly = false } = options;

    try {
      const response = await this.api.get(`/users/${userId}/notifications`, {
        params: { page, limit, unreadOnly }
      });

      return {
        notifications: response.notifications.map(this.processNotification),
        totalCount: response.totalCount,
        unreadCount: response.unreadCount,
        currentPage: page,
        totalPages: Math.ceil(response.totalCount / limit)
      };
    } catch (error) {
      throw this.handleUserError(error);
    }
  }

  async markNotificationAsRead(userId, notificationId) {
    if (!userId || !notificationId) {
      throw new Error('User ID and notification ID are required');
    }

    try {
      await this.api.patch(`/users/${userId}/notifications/${notificationId}`, {
        read: true,
        readAt: new Date().toISOString()
      });

      return { success: true };
    } catch (error) {
      throw this.handleUserError(error);
    }
  }

  async markAllNotificationsAsRead(userId) {
    if (!userId) {
      throw new Error('User ID is required');
    }

    try {
      await this.api.patch(`/users/${userId}/notifications/mark-all-read`);
      return { success: true };
    } catch (error) {
      throw this.handleUserError(error);
    }
  }

  async deleteNotification(userId, notificationId) {
    if (!userId || !notificationId) {
      throw new Error('User ID and notification ID are required');
    }

    try {
      await this.api.delete(`/users/${userId}/notifications/${notificationId}`);
      return { success: true };
    } catch (error) {
      throw this.handleUserError(error);
    }
  }

  async getUserActivityLog(userId, options = {}) {
    if (!userId) {
      throw new Error('User ID is required');
    }

    const { page = 1, limit = 50, startDate, endDate, activityType } = options;

    try {
      const params = { page, limit };
      if (startDate) params.startDate = startDate;
      if (endDate) params.endDate = endDate;
      if (activityType) params.activityType = activityType;

      const response = await this.api.get(`/users/${userId}/activity-log`, { params });

      return {
        activities: response.activities.map(this.processActivity),
        totalCount: response.totalCount,
        currentPage: page,
        totalPages: Math.ceil(response.totalCount / limit)
      };
    } catch (error) {
      throw this.handleUserError(error);
    }
  }

  async updateSecuritySettings(userId, settings) {
    if (!userId) {
      throw new Error('User ID is required');
    }

    this.validateSecuritySettings(settings);

    try {
      const response = await this.api.put(`/users/${userId}/security`, settings);
      return {
        success: true,
        settings: response.settings,
        message: 'Security settings updated successfully'
      };
    } catch (error) {
      throw this.handleUserError(error);
    }
  }

  async getUserSessions(userId) {
    if (!userId) {
      throw new Error('User ID is required');
    }

    try {
      const response = await this.api.get(`/users/${userId}/sessions`);
      return response.sessions.map(this.processSession);
    } catch (error) {
      throw this.handleUserError(error);
    }
  }

  async terminateSession(userId, sessionId) {
    if (!userId || !sessionId) {
      throw new Error('User ID and session ID are required');
    }

    try {
      await this.api.delete(`/users/${userId}/sessions/${sessionId}`);
      return { success: true };
    } catch (error) {
      throw this.handleUserError(error);
    }
  }

  async terminateAllSessions(userId, excludeCurrent = true) {
    if (!userId) {
      throw new Error('User ID is required');
    }

    try {
      await this.api.delete(`/users/${userId}/sessions`, {
        params: { excludeCurrent }
      });
      return { success: true };
    } catch (error) {
      throw this.handleUserError(error);
    }
  }

  async exportUserData(userId, dataTypes = []) {
    if (!userId) {
      throw new Error('User ID is required');
    }

    const validDataTypes = ['profile', 'preferences', 'notifications', 'activity', 'portfolios', 'transactions'];
    const requestedTypes = dataTypes.length > 0 ? dataTypes : validDataTypes;

    // Validate data types
    const invalidTypes = requestedTypes.filter(type => !validDataTypes.includes(type));
    if (invalidTypes.length > 0) {
      throw new Error(`Invalid data types: ${invalidTypes.join(', ')}`);
    }

    try {
      const response = await this.api.post(`/users/${userId}/export`, {
        dataTypes: requestedTypes
      });

      return {
        success: true,
        exportId: response.exportId,
        downloadUrl: response.downloadUrl,
        expiresAt: response.expiresAt,
        message: 'Data export initiated. You will receive a download link via email.'
      };
    } catch (error) {
      throw this.handleUserError(error);
    }
  }

  async deleteUserAccount(userId, confirmation) {
    if (!userId) {
      throw new Error('User ID is required');
    }

    if (!confirmation || confirmation !== 'DELETE_ACCOUNT') {
      throw new Error('Account deletion must be confirmed with "DELETE_ACCOUNT"');
    }

    try {
      await this.api.delete(`/users/${userId}`, {
        data: { confirmation }
      });

      // Clear all cached data
      this.clearUserCache();

      return {
        success: true,
        message: 'Account deleted successfully'
      };
    } catch (error) {
      throw this.handleUserError(error);
    }
  }

  // Helper methods
  processUserProfile(data) {
    return {
      id: data.id,
      firstName: data.firstName,
      lastName: data.lastName,
      email: data.email,
      phone: data.phone,
      dateOfBirth: data.dateOfBirth,
      address: data.address ? {
        street: data.address.street,
        city: data.address.city,
        state: data.address.state,
        zipCode: data.address.zipCode,
        country: data.address.country
      } : null,
      profilePictureUrl: data.profilePictureUrl,
      bio: data.bio,
      website: data.website,
      linkedIn: data.linkedIn,
      twitter: data.twitter,
      occupation: data.occupation,
      employer: data.employer,
      annualIncome: data.annualIncome,
      investmentExperience: data.investmentExperience,
      riskTolerance: data.riskTolerance,
      investmentGoals: data.investmentGoals || [],
      createdAt: data.createdAt,
      updatedAt: data.updatedAt,
      lastLoginAt: data.lastLoginAt,
      emailVerified: data.emailVerified || false,
      phoneVerified: data.phoneVerified || false,
      kycStatus: data.kycStatus || 'pending',
      accountStatus: data.accountStatus || 'active'
    };
  }

  processUserPreferences(data, userId) {
    return {
      userId,
      theme: data.theme || 'light',
      language: data.language || 'en',
      currency: data.currency || 'USD',
      timezone: data.timezone || 'UTC',
      dateFormat: data.dateFormat || 'MM/DD/YYYY',
      numberFormat: data.numberFormat || 'US',
      notifications: {
        email: {
          portfolioUpdates: data.notifications?.email?.portfolioUpdates !== false,
          tradeConfirmations: data.notifications?.email?.tradeConfirmations !== false,
          marketAlerts: data.notifications?.email?.marketAlerts !== false,
          securityAlerts: data.notifications?.email?.securityAlerts !== false,
          promotions: data.notifications?.email?.promotions || false
        },
        push: {
          portfolioUpdates: data.notifications?.push?.portfolioUpdates || false,
          tradeConfirmations: data.notifications?.push?.tradeConfirmations !== false,
          marketAlerts: data.notifications?.push?.marketAlerts || false,
          securityAlerts: data.notifications?.push?.securityAlerts !== false
        },
        sms: {
          securityAlerts: data.notifications?.sms?.securityAlerts || false,
          tradeConfirmations: data.notifications?.sms?.tradeConfirmations || false
        }
      },
      dashboard: {
        layout: data.dashboard?.layout || 'default',
        widgets: data.dashboard?.widgets || [],
        refreshInterval: data.dashboard?.refreshInterval || 30
      },
      trading: {
        defaultOrderType: data.trading?.defaultOrderType || 'market',
        confirmations: data.trading?.confirmations !== false,
        advancedMode: data.trading?.advancedMode || false
      },
      privacy: {
        profileVisibility: data.privacy?.profileVisibility || 'private',
        showPortfolioPerformance: data.privacy?.showPortfolioPerformance || false,
        allowAnalytics: data.privacy?.allowAnalytics !== false
      },
      updatedAt: data.updatedAt || new Date().toISOString()
    };
  }

  processNotification(notification) {
    return {
      id: notification.id,
      type: notification.type,
      title: notification.title,
      message: notification.message,
      data: notification.data || {},
      read: notification.read || false,
      priority: notification.priority || 'normal',
      category: notification.category || 'general',
      actionUrl: notification.actionUrl,
      expiresAt: notification.expiresAt,
      createdAt: notification.createdAt,
      readAt: notification.readAt
    };
  }

  processActivity(activity) {
    return {
      id: activity.id,
      type: activity.type,
      description: activity.description,
      details: activity.details || {},
      ipAddress: activity.ipAddress,
      userAgent: activity.userAgent,
      location: activity.location,
      timestamp: activity.timestamp,
      sessionId: activity.sessionId
    };
  }

  processSession(session) {
    return {
      id: session.id,
      deviceType: session.deviceType,
      deviceName: session.deviceName,
      browser: session.browser,
      operatingSystem: session.operatingSystem,
      ipAddress: session.ipAddress,
      location: session.location,
      current: session.current || false,
      createdAt: session.createdAt,
      lastActiveAt: session.lastActiveAt,
      expiresAt: session.expiresAt
    };
  }

  validateProfileData(data) {
    if (!data || typeof data !== 'object') {
      throw new Error('Profile data is required');
    }

    if (data.firstName && (data.firstName.length < 1 || data.firstName.length > 50)) {
      throw new Error('First name must be 1-50 characters');
    }

    if (data.lastName && (data.lastName.length < 1 || data.lastName.length > 50)) {
      throw new Error('Last name must be 1-50 characters');
    }

    if (data.email && !this.isValidEmail(data.email)) {
      throw new Error('Invalid email format');
    }

    if (data.phone && !this.isValidPhone(data.phone)) {
      throw new Error('Invalid phone format');
    }

    if (data.dateOfBirth && !this.isValidDate(data.dateOfBirth)) {
      throw new Error('Invalid date of birth');
    }

    if (data.website && !this.isValidUrl(data.website)) {
      throw new Error('Invalid website URL');
    }

    if (data.annualIncome && (data.annualIncome < 0 || data.annualIncome > 10000000)) {
      throw new Error('Annual income must be between $0 and $10,000,000');
    }

    const validRiskLevels = ['conservative', 'moderate', 'aggressive'];
    if (data.riskTolerance && !validRiskLevels.includes(data.riskTolerance)) {
      throw new Error('Invalid risk tolerance level');
    }

    const validExperienceLevels = ['beginner', 'intermediate', 'advanced', 'expert'];
    if (data.investmentExperience && !validExperienceLevels.includes(data.investmentExperience)) {
      throw new Error('Invalid investment experience level');
    }
  }

  validatePreferences(preferences) {
    if (!preferences || typeof preferences !== 'object') {
      throw new Error('Preferences data is required');
    }

    const validThemes = ['light', 'dark', 'auto'];
    if (preferences.theme && !validThemes.includes(preferences.theme)) {
      throw new Error('Invalid theme');
    }

    const validLanguages = ['en', 'es', 'fr', 'de', 'it', 'pt', 'ja', 'zh'];
    if (preferences.language && !validLanguages.includes(preferences.language)) {
      throw new Error('Invalid language');
    }

    const validCurrencies = ['USD', 'EUR', 'GBP', 'JPY', 'CAD', 'AUD'];
    if (preferences.currency && !validCurrencies.includes(preferences.currency)) {
      throw new Error('Invalid currency');
    }

    if (preferences.dashboard?.refreshInterval) {
      const interval = preferences.dashboard.refreshInterval;
      if (interval < 5 || interval > 300) {
        throw new Error('Refresh interval must be between 5 and 300 seconds');
      }
    }
  }

  validateSecuritySettings(settings) {
    if (!settings || typeof settings !== 'object') {
      throw new Error('Security settings are required');
    }

    if (settings.sessionTimeout && (settings.sessionTimeout < 15 || settings.sessionTimeout > 480)) {
      throw new Error('Session timeout must be between 15 and 480 minutes');
    }

    if (settings.loginNotifications !== undefined && typeof settings.loginNotifications !== 'boolean') {
      throw new Error('Login notifications must be a boolean');
    }

    if (settings.twoFactorAuth !== undefined && typeof settings.twoFactorAuth !== 'boolean') {
      throw new Error('Two-factor authentication must be a boolean');
    }
  }

  isValidImageFile(file) {
    const validTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
    const maxSize = 5 * 1024 * 1024; // 5MB

    return file && 
           validTypes.includes(file.type) && 
           file.size <= maxSize;
  }

  isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  }

  isValidPhone(phone) {
    const phoneRegex = /^\+?[\d\s\-\(\)]{10,}$/;
    return phoneRegex.test(phone);
  }

  isValidDate(dateString) {
    const date = new Date(dateString);
    return date instanceof Date && !isNaN(date.getTime());
  }

  isValidUrl(url) {
    try {
      new URL(url);
      return true;
    } catch {
      return false;
    }
  }

  clearUserCache() {
    this.storage.removeItem(this.userCacheKey);
    this.storage.removeItem(this.preferencesCacheKey);
  }

  handleUserError(error) {
    if (error.response?.status === 404) {
      return new Error('User not found');
    }

    if (error.response?.status === 403) {
      return new Error('Access denied');
    }

    if (error.response?.status === 409) {
      return new Error('User data conflict');
    }

    if (error.response?.data?.message) {
      return new Error(error.response.data.message);
    }

    return new Error(error.message || 'User service error');
  }
}

describe('👤 User Service', () => {
  let userService;
  let mockApi;
  let mockStorage;

  const mockUser = {
    id: '1',
    firstName: 'John',
    lastName: 'Doe',
    email: 'john@example.com',
    phone: '+1234567890',
    profilePictureUrl: 'https://example.com/avatar.jpg',
    riskTolerance: 'moderate',
    investmentExperience: 'intermediate',
    createdAt: '2024-01-01T00:00:00Z',
    emailVerified: true,
    kycStatus: 'approved'
  };

  const mockPreferences = {
    theme: 'dark',
    language: 'en',
    currency: 'USD',
    notifications: {
      email: { portfolioUpdates: true }
    }
  };

  beforeEach(() => {
    mockApi = {
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
      patch: vi.fn()
    };

    mockStorage = {
      setItem: vi.fn(),
      getItem: vi.fn(),
      removeItem: vi.fn()
    };

    userService = new UserService(mockApi, mockStorage);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('User Profile', () => {
    it('should get user profile successfully', async () => {
      mockApi.get.mockResolvedValue(mockUser);

      const result = await userService.getUserProfile('1');

      expect(mockApi.get).toHaveBeenCalledWith('/users/1/profile');
      expect(result.id).toBe('1');
      expect(result.firstName).toBe('John');
      expect(result.email).toBe('john@example.com');
      expect(mockStorage.setItem).toHaveBeenCalled();
    });

    it('should update user profile successfully', async () => {
      const updateData = {
        firstName: 'Jane',
        lastName: 'Smith',
        phone: '+9876543210'
      };

      const updatedUser = { ...mockUser, ...updateData };
      mockApi.put.mockResolvedValue(updatedUser);

      const result = await userService.updateUserProfile('1', updateData);

      expect(mockApi.put).toHaveBeenCalledWith('/users/1/profile', updateData);
      expect(result.firstName).toBe('Jane');
      expect(result.lastName).toBe('Smith');
    });

    it('should validate profile data', async () => {
      await expect(userService.updateUserProfile('1', {
        firstName: ''
      })).rejects.toThrow('First name must be 1-50 characters');

      await expect(userService.updateUserProfile('1', {
        email: 'invalid-email'
      })).rejects.toThrow('Invalid email format');

      await expect(userService.updateUserProfile('1', {
        annualIncome: -1000
      })).rejects.toThrow('Annual income must be between $0 and $10,000,000');
    });

    it('should validate user ID requirement', async () => {
      await expect(userService.getUserProfile()).rejects.toThrow('User ID is required');
      await expect(userService.updateUserProfile()).rejects.toThrow('User ID is required');
    });
  });

  describe('Profile Picture Upload', () => {
    it('should upload profile picture successfully', async () => {
      const mockFile = new File(['image data'], 'avatar.jpg', { type: 'image/jpeg' });
      mockApi.post.mockResolvedValue({
        imageUrl: 'https://example.com/new-avatar.jpg'
      });

      const result = await userService.uploadProfilePicture('1', mockFile);

      expect(mockApi.post).toHaveBeenCalledWith('/users/1/profile-picture', expect.any(FormData), {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      expect(result.success).toBe(true);
      expect(result.imageUrl).toBe('https://example.com/new-avatar.jpg');
    });

    it('should validate image file', async () => {
      const invalidFile = new File(['text'], 'document.txt', { type: 'text/plain' });

      await expect(userService.uploadProfilePicture('1', invalidFile))
        .rejects.toThrow('Valid image file is required');

      await expect(userService.uploadProfilePicture('1', null))
        .rejects.toThrow('Valid image file is required');
    });
  });

  describe('User Preferences', () => {
    it('should get user preferences successfully', async () => {
      mockApi.get.mockResolvedValue(mockPreferences);

      const result = await userService.getUserPreferences('1');

      expect(mockApi.get).toHaveBeenCalledWith('/users/1/preferences');
      expect(result.theme).toBe('dark');
      expect(result.currency).toBe('USD');
      expect(mockStorage.setItem).toHaveBeenCalled();
    });

    it('should use cached preferences when available', async () => {
      const cachedPreferences = { userId: '1', theme: 'light' };
      mockStorage.getItem.mockReturnValue(JSON.stringify(cachedPreferences));

      const result = await userService.getUserPreferences('1');

      expect(mockApi.get).not.toHaveBeenCalled();
      expect(result.theme).toBe('light');
    });

    it('should update user preferences successfully', async () => {
      const newPreferences = { theme: 'light', language: 'es' };
      mockApi.put.mockResolvedValue(newPreferences);

      const result = await userService.updateUserPreferences('1', newPreferences);

      expect(mockApi.put).toHaveBeenCalledWith('/users/1/preferences', newPreferences);
      expect(result.theme).toBe('light');
      expect(result.language).toBe('es');
    });

    it('should validate preferences data', async () => {
      await expect(userService.updateUserPreferences('1', {
        theme: 'invalid'
      })).rejects.toThrow('Invalid theme');

      await expect(userService.updateUserPreferences('1', {
        currency: 'INVALID'
      })).rejects.toThrow('Invalid currency');

      await expect(userService.updateUserPreferences('1', {
        dashboard: { refreshInterval: 1 }
      })).rejects.toThrow('Refresh interval must be between 5 and 300 seconds');
    });
  });

  describe('Notifications', () => {
    it('should get user notifications successfully', async () => {
      const mockNotifications = {
        notifications: [
          { id: '1', title: 'Test', message: 'Test message', read: false },
          { id: '2', title: 'Test 2', message: 'Test message 2', read: true }
        ],
        totalCount: 2,
        unreadCount: 1
      };

      mockApi.get.mockResolvedValue(mockNotifications);

      const result = await userService.getUserNotifications('1', { page: 1, limit: 10 });

      expect(mockApi.get).toHaveBeenCalledWith('/users/1/notifications', {
        params: { page: 1, limit: 10, unreadOnly: false }
      });
      expect(result.notifications).toHaveLength(2);
      expect(result.unreadCount).toBe(1);
    });

    it('should mark notification as read', async () => {
      mockApi.patch.mockResolvedValue({ success: true });

      const result = await userService.markNotificationAsRead('1', 'notif1');

      expect(mockApi.patch).toHaveBeenCalledWith('/users/1/notifications/notif1', {
        read: true,
        readAt: expect.any(String)
      });
      expect(result.success).toBe(true);
    });

    it('should mark all notifications as read', async () => {
      mockApi.patch.mockResolvedValue({ success: true });

      const result = await userService.markAllNotificationsAsRead('1');

      expect(mockApi.patch).toHaveBeenCalledWith('/users/1/notifications/mark-all-read');
      expect(result.success).toBe(true);
    });

    it('should delete notification', async () => {
      mockApi.delete.mockResolvedValue({ success: true });

      const result = await userService.deleteNotification('1', 'notif1');

      expect(mockApi.delete).toHaveBeenCalledWith('/users/1/notifications/notif1');
      expect(result.success).toBe(true);
    });
  });

  describe('Activity Log', () => {
    it('should get user activity log successfully', async () => {
      const mockActivities = {
        activities: [
          { id: '1', type: 'login', description: 'User logged in', timestamp: '2024-01-01T10:00:00Z' },
          { id: '2', type: 'trade', description: 'Bought AAPL', timestamp: '2024-01-01T11:00:00Z' }
        ],
        totalCount: 2
      };

      mockApi.get.mockResolvedValue(mockActivities);

      const result = await userService.getUserActivityLog('1', {
        page: 1,
        limit: 50,
        activityType: 'trade'
      });

      expect(mockApi.get).toHaveBeenCalledWith('/users/1/activity-log', {
        params: { page: 1, limit: 50, activityType: 'trade' }
      });
      expect(result.activities).toHaveLength(2);
      expect(result.totalCount).toBe(2);
    });
  });

  describe('Security Settings', () => {
    it('should update security settings successfully', async () => {
      const securitySettings = {
        sessionTimeout: 60,
        loginNotifications: true,
        twoFactorAuth: true
      };

      mockApi.put.mockResolvedValue({ settings: securitySettings });

      const result = await userService.updateSecuritySettings('1', securitySettings);

      expect(mockApi.put).toHaveBeenCalledWith('/users/1/security', securitySettings);
      expect(result.success).toBe(true);
      expect(result.settings).toEqual(securitySettings);
    });

    it('should validate security settings', async () => {
      await expect(userService.updateSecuritySettings('1', {
        sessionTimeout: 5
      })).rejects.toThrow('Session timeout must be between 15 and 480 minutes');

      await expect(userService.updateSecuritySettings('1', {
        loginNotifications: 'invalid'
      })).rejects.toThrow('Login notifications must be a boolean');
    });
  });

  describe('Session Management', () => {
    it('should get user sessions successfully', async () => {
      const mockSessions = {
        sessions: [
          { id: '1', deviceType: 'desktop', current: true, createdAt: '2024-01-01T10:00:00Z' },
          { id: '2', deviceType: 'mobile', current: false, createdAt: '2024-01-01T09:00:00Z' }
        ]
      };

      mockApi.get.mockResolvedValue(mockSessions);

      const result = await userService.getUserSessions('1');

      expect(mockApi.get).toHaveBeenCalledWith('/users/1/sessions');
      expect(result).toHaveLength(2);
      expect(result[0].current).toBe(true);
    });

    it('should terminate specific session', async () => {
      mockApi.delete.mockResolvedValue({ success: true });

      const result = await userService.terminateSession('1', 'session1');

      expect(mockApi.delete).toHaveBeenCalledWith('/users/1/sessions/session1');
      expect(result.success).toBe(true);
    });

    it('should terminate all sessions', async () => {
      mockApi.delete.mockResolvedValue({ success: true });

      const result = await userService.terminateAllSessions('1', false);

      expect(mockApi.delete).toHaveBeenCalledWith('/users/1/sessions', {
        params: { excludeCurrent: false }
      });
      expect(result.success).toBe(true);
    });
  });

  describe('Data Export', () => {
    it('should export user data successfully', async () => {
      const mockExport = {
        exportId: 'export123',
        downloadUrl: 'https://example.com/download/export123',
        expiresAt: '2024-01-02T00:00:00Z'
      };

      mockApi.post.mockResolvedValue(mockExport);

      const result = await userService.exportUserData('1', ['profile', 'preferences']);

      expect(mockApi.post).toHaveBeenCalledWith('/users/1/export', {
        dataTypes: ['profile', 'preferences']
      });
      expect(result.success).toBe(true);
      expect(result.exportId).toBe('export123');
    });

    it('should validate data types for export', async () => {
      await expect(userService.exportUserData('1', ['invalid_type']))
        .rejects.toThrow('Invalid data types: invalid_type');
    });
  });

  describe('Account Deletion', () => {
    it('should delete account with proper confirmation', async () => {
      mockApi.delete.mockResolvedValue({ success: true });

      const result = await userService.deleteUserAccount('1', 'DELETE_ACCOUNT');

      expect(mockApi.delete).toHaveBeenCalledWith('/users/1', {
        data: { confirmation: 'DELETE_ACCOUNT' }
      });
      expect(result.success).toBe(true);
      expect(mockStorage.removeItem).toHaveBeenCalled();
    });

    it('should require proper confirmation for account deletion', async () => {
      await expect(userService.deleteUserAccount('1', 'wrong'))
        .rejects.toThrow('Account deletion must be confirmed with "DELETE_ACCOUNT"');

      await expect(userService.deleteUserAccount('1'))
        .rejects.toThrow('Account deletion must be confirmed with "DELETE_ACCOUNT"');
    });
  });

  describe('Validation Helpers', () => {
    it('should validate image files correctly', () => {
      const validFile = new File(['image'], 'test.jpg', { type: 'image/jpeg' });
      expect(userService.isValidImageFile(validFile)).toBe(true);

      const invalidFile = new File(['text'], 'test.txt', { type: 'text/plain' });
      expect(userService.isValidImageFile(invalidFile)).toBe(false);

      expect(userService.isValidImageFile(null)).toBe(false);
    });

    it('should validate URLs correctly', () => {
      expect(userService.isValidUrl('https://example.com')).toBe(true);
      expect(userService.isValidUrl('http://test.com')).toBe(true);
      expect(userService.isValidUrl('not-a-url')).toBe(false);
      expect(userService.isValidUrl('')).toBe(false);
    });

    it('should validate dates correctly', () => {
      expect(userService.isValidDate('2024-01-01')).toBe(true);
      expect(userService.isValidDate('2024-01-01T10:00:00Z')).toBe(true);
      expect(userService.isValidDate('invalid-date')).toBe(false);
    });
  });

  describe('Error Handling', () => {
    it('should handle different HTTP error codes', () => {
      const error404 = { response: { status: 404 } };
      const error403 = { response: { status: 403 } };
      const error409 = { response: { status: 409 } };
      const errorWithMessage = { response: { data: { message: 'Custom error' } } };

      expect(userService.handleUserError(error404).message).toBe('User not found');
      expect(userService.handleUserError(error403).message).toBe('Access denied');
      expect(userService.handleUserError(error409).message).toBe('User data conflict');
      expect(userService.handleUserError(errorWithMessage).message).toBe('Custom error');
    });

    it('should handle API errors gracefully', async () => {
      mockApi.get.mockRejectedValue(new Error('Network error'));

      await expect(userService.getUserProfile('1'))
        .rejects.toThrow('Network error');
    });

    it('should handle invalid cache data', async () => {
      mockStorage.getItem.mockReturnValue('invalid-json');
      mockApi.get.mockResolvedValue(mockPreferences);

      const result = await userService.getUserPreferences('1');

      expect(mockApi.get).toHaveBeenCalled();
      expect(result.theme).toBe('dark');
    });
  });
});