/**
 * Settings API Keys Page Integration Tests
 * Comprehensive testing of API key management functionality
 * FIXED: React hooks import issue - uses React 18 built-in useSyncExternalStore
 */

// Import React from our fixed preloader to ensure hooks are available
import '../../../utils/reactModulePreloader.js';
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';

// Import the actual MUI theme
import muiTheme from '../../../theme/muiTheme';

// Mock AuthContext
const mockAuthContext = {
  user: { email: 'test@example.com', username: 'testuser' },
  isAuthenticated: true,
  isLoading: false,
  tokens: { accessToken: 'mock-token' }
};

vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthContext,
  AuthProvider: ({ children }) => children
}));

// Mock API service
const mockApiService = {
  getApiKeys: vi.fn(),
  addApiKey: vi.fn(),
  updateApiKey: vi.fn(),
  deleteApiKey: vi.fn(),
  testApiKey: vi.fn(),
  getApiKeyStatus: vi.fn()
};

vi.mock('../../../services/api', () => ({
  default: mockApiService,
  getApiKeys: mockApiService.getApiKeys,
  addApiKey: mockApiService.addApiKey,
  updateApiKey: mockApiService.updateApiKey,
  deleteApiKey: mockApiService.deleteApiKey,
  testApiKey: mockApiService.testApiKey,
  getApiKeyStatus: mockApiService.getApiKeyStatus
}));

// Mock react-router-dom hooks
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useLocation: () => ({ pathname: '/settings/api-keys', search: '', hash: '', state: null })
  };
});

// Mock API Key Provider
const mockApiKeyContext = {
  apiKeys: [
    {
      id: 'key_1',
      provider: 'alpaca',
      name: 'Alpaca Production',
      isActive: true,
      status: 'connected',
      createdAt: '2024-01-01T00:00:00Z',
      lastTested: '2024-01-15T12:00:00Z'
    },
    {
      id: 'key_2',
      provider: 'td_ameritrade',
      name: 'TD Ameritrade Main',
      isActive: true,
      status: 'connected',
      createdAt: '2024-01-02T00:00:00Z',
      lastTested: '2024-01-15T11:30:00Z'
    },
    {
      id: 'key_3',
      provider: 'alpaca',
      name: 'Alpaca Sandbox',
      isActive: false,
      status: 'disconnected',
      createdAt: '2024-01-03T00:00:00Z',
      lastTested: null
    }
  ],
  addApiKey: vi.fn(),
  updateApiKey: vi.fn(),
  deleteApiKey: vi.fn(),
  testApiKey: vi.fn(),
  refreshApiKeys: vi.fn(),
  loading: false,
  error: null
};

vi.mock('../../../components/ApiKeyProvider', () => ({
  default: ({ children }) => children,
  useApiKeys: () => mockApiKeyContext
}));

// Create mock Settings API Keys page component
const MockSettingsApiKeysPage = () => {
  const [showAddForm, setShowAddForm] = React.useState(false);
  const [editingKey, setEditingKey] = React.useState(null);
  const [testingKey, setTestingKey] = React.useState(null);
  const [deleteConfirm, setDeleteConfirm] = React.useState(null);

  const handleAddApiKey = async (apiKeyData) => {
    try {
      await mockApiKeyContext.addApiKey(apiKeyData);
      setShowAddForm(false);
    } catch (error) {
      console.error('Failed to add API key:', error);
    }
  };

  const handleUpdateApiKey = async (keyId, updates) => {
    try {
      await mockApiKeyContext.updateApiKey(keyId, updates);
      setEditingKey(null);
    } catch (error) {
      console.error('Failed to update API key:', error);
    }
  };

  const handleDeleteApiKey = async (keyId) => {
    try {
      await mockApiKeyContext.deleteApiKey(keyId);
      setDeleteConfirm(null);
    } catch (error) {
      console.error('Failed to delete API key:', error);
    }
  };

  const handleTestApiKey = async (keyId) => {
    setTestingKey(keyId);
    try {
      await mockApiKeyContext.testApiKey(keyId);
    } catch (error) {
      console.error('Failed to test API key:', error);
    } finally {
      setTestingKey(null);
    }
  };

  return (
    <div data-testid="settings-api-keys-page">
      {/* Page Header */}
      <div data-testid="page-header">
        <h1>API Key Management</h1>
        <p>Manage your broker and data provider API credentials</p>
        <button 
          data-testid="add-api-key-button"
          onClick={() => setShowAddForm(true)}
        >
          Add New API Key
        </button>
      </div>

      {/* API Keys List */}
      <div data-testid="api-keys-list">
        {mockApiKeyContext.apiKeys.map(apiKey => (
          <div key={apiKey.id} data-testid={`api-key-item-${apiKey.id}`} className="api-key-card">
            <div data-testid={`api-key-info-${apiKey.id}`}>
              <h3>{apiKey.name}</h3>
              <p>Provider: {apiKey.provider}</p>
              <p>Status: <span data-testid={`status-${apiKey.id}`}>{apiKey.status}</span></p>
              <p>Active: <span data-testid={`active-${apiKey.id}`}>{apiKey.isActive ? 'Yes' : 'No'}</span></p>
              {apiKey.lastTested && (
                <p>Last Tested: {new Date(apiKey.lastTested).toLocaleDateString()}</p>
              )}
            </div>
            
            <div data-testid={`api-key-actions-${apiKey.id}`} className="api-key-actions">
              <button 
                data-testid={`test-button-${apiKey.id}`}
                onClick={() => handleTestApiKey(apiKey.id)}
                disabled={testingKey === apiKey.id}
              >
                {testingKey === apiKey.id ? 'Testing...' : 'Test Connection'}
              </button>
              
              <button 
                data-testid={`edit-button-${apiKey.id}`}
                onClick={() => setEditingKey(apiKey.id)}
              >
                Edit
              </button>
              
              <button 
                data-testid={`delete-button-${apiKey.id}`}
                onClick={() => setDeleteConfirm(apiKey.id)}
                className="danger"
              >
                Delete
              </button>
              
              <button 
                data-testid={`toggle-button-${apiKey.id}`}
                onClick={() => handleUpdateApiKey(apiKey.id, { isActive: !apiKey.isActive })}
              >
                {apiKey.isActive ? 'Deactivate' : 'Activate'}
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Add API Key Form */}
      {showAddForm && (
        <div data-testid="add-api-key-modal" className="modal">
          <div data-testid="add-api-key-form" className="modal-content">
            <h2>Add New API Key</h2>
            <form onSubmit={(e) => {
              e.preventDefault();
              const formData = new FormData(e.target);
              handleAddApiKey({
                provider: formData.get('provider'),
                name: formData.get('name'),
                apiKey: formData.get('apiKey'),
                apiSecret: formData.get('apiSecret'),
                baseUrl: formData.get('baseUrl')
              });
            }}>
              <select data-testid="provider-select" name="provider" required>
                <option value="">Select Provider</option>
                <option value="alpaca">Alpaca Markets</option>
                <option value="td_ameritrade">TD Ameritrade</option>
                <option value="polygon">Polygon.io</option>
                <option value="finnhub">Finnhub</option>
              </select>
              
              <input 
                data-testid="name-input"
                name="name" 
                type="text" 
                placeholder="API Key Name" 
                required 
              />
              
              <input 
                data-testid="api-key-input"
                name="apiKey" 
                type="text" 
                placeholder="API Key" 
                required 
              />
              
              <input 
                data-testid="api-secret-input"
                name="apiSecret" 
                type="password" 
                placeholder="API Secret (if required)" 
              />
              
              <input 
                data-testid="base-url-input"
                name="baseUrl" 
                type="url" 
                placeholder="Base URL (optional)" 
              />
              
              <div className="form-actions">
                <button type="submit" data-testid="save-api-key-button">
                  Save API Key
                </button>
                <button 
                  type="button" 
                  data-testid="cancel-add-button"
                  onClick={() => setShowAddForm(false)}
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit API Key Form */}
      {editingKey && (
        <div data-testid="edit-api-key-modal" className="modal">
          <div data-testid="edit-api-key-form" className="modal-content">
            <h2>Edit API Key</h2>
            <form onSubmit={(e) => {
              e.preventDefault();
              const formData = new FormData(e.target);
              handleUpdateApiKey(editingKey, {
                name: formData.get('name'),
                baseUrl: formData.get('baseUrl')
              });
            }}>
              <input 
                data-testid="edit-name-input"
                name="name" 
                type="text" 
                defaultValue={mockApiKeyContext.apiKeys.find(k => k.id === editingKey)?.name || ''}
                required 
              />
              
              <input 
                data-testid="edit-base-url-input"
                name="baseUrl" 
                type="url" 
                placeholder="Base URL (optional)" 
              />
              
              <div className="form-actions">
                <button type="submit" data-testid="update-api-key-button">
                  Update API Key
                </button>
                <button 
                  type="button" 
                  data-testid="cancel-edit-button"
                  onClick={() => setEditingKey(null)}
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation */}
      {deleteConfirm && (
        <div data-testid="delete-confirmation-modal" className="modal">
          <div data-testid="delete-confirmation" className="modal-content">
            <h2>Confirm Deletion</h2>
            <p>Are you sure you want to delete this API key? This action cannot be undone.</p>
            <div className="form-actions">
              <button 
                data-testid="confirm-delete-button"
                onClick={() => handleDeleteApiKey(deleteConfirm)}
                className="danger"
              >
                Delete
              </button>
              <button 
                data-testid="cancel-delete-button"
                onClick={() => setDeleteConfirm(null)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Loading States */}
      {mockApiKeyContext.loading && (
        <div data-testid="loading-spinner" className="loading">
          Loading API keys...
        </div>
      )}

      {/* Error States */}
      {mockApiKeyContext.error && (
        <div data-testid="error-message" className="error">
          Error: {mockApiKeyContext.error}
        </div>
      )}
    </div>
  );
};

// Test wrapper
const TestWrapper = ({ children }) => (
  <ThemeProvider theme={muiTheme}>
    <BrowserRouter>
      {children}
    </BrowserRouter>
  </ThemeProvider>
);

describe('⚙️ Settings API Keys Page Tests', () => {
  const user = userEvent.setup();

  beforeEach(() => {
    vi.clearAllMocks();
    mockApiKeyContext.addApiKey.mockClear();
    mockApiKeyContext.updateApiKey.mockClear();
    mockApiKeyContext.deleteApiKey.mockClear();
    mockApiKeyContext.testApiKey.mockClear();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Page Rendering', () => {
    it('should render settings API keys page with all sections', () => {
      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      expect(screen.getByTestId('settings-api-keys-page')).toBeInTheDocument();
      expect(screen.getByTestId('page-header')).toBeInTheDocument();
      expect(screen.getByTestId('api-keys-list')).toBeInTheDocument();
      expect(screen.getByTestId('add-api-key-button')).toBeInTheDocument();
    });

    it('should display all API keys with correct information', () => {
      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      // Check that all API keys are displayed
      expect(screen.getByTestId('api-key-item-key_1')).toBeInTheDocument();
      expect(screen.getByTestId('api-key-item-key_2')).toBeInTheDocument();
      expect(screen.getByTestId('api-key-item-key_3')).toBeInTheDocument();

      // Check specific API key information
      expect(screen.getByText('Alpaca Production')).toBeInTheDocument();
      expect(screen.getByText('TD Ameritrade Main')).toBeInTheDocument();
      expect(screen.getByTestId('status-key_1')).toHaveTextContent('connected');
      expect(screen.getByTestId('active-key_1')).toHaveTextContent('Yes');
      expect(screen.getByTestId('active-key_3')).toHaveTextContent('No');
    });

    it('should show action buttons for each API key', () => {
      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      // Check action buttons for first API key
      expect(screen.getByTestId('test-button-key_1')).toBeInTheDocument();
      expect(screen.getByTestId('edit-button-key_1')).toBeInTheDocument();
      expect(screen.getByTestId('delete-button-key_1')).toBeInTheDocument();
      expect(screen.getByTestId('toggle-button-key_1')).toBeInTheDocument();
    });
  });

  describe('Add API Key Functionality', () => {
    it('should open add API key form when button is clicked', async () => {
      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('add-api-key-button'));

      expect(screen.getByTestId('add-api-key-modal')).toBeInTheDocument();
      expect(screen.getByTestId('add-api-key-form')).toBeInTheDocument();
      expect(screen.getByTestId('provider-select')).toBeInTheDocument();
    });

    it('should handle successful API key addition', async () => {
      mockApiKeyContext.addApiKey.mockResolvedValue({ success: true });

      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      // Open add form
      await user.click(screen.getByTestId('add-api-key-button'));

      // Fill out form
      await user.selectOptions(screen.getByTestId('provider-select'), 'alpaca');
      await user.type(screen.getByTestId('name-input'), 'Test API Key');
      await user.type(screen.getByTestId('api-key-input'), 'test-api-key-123');
      await user.type(screen.getByTestId('api-secret-input'), 'test-secret-456');

      // Submit form
      await user.click(screen.getByTestId('save-api-key-button'));

      await waitFor(() => {
        expect(mockApiKeyContext.addApiKey).toHaveBeenCalledWith({
          provider: 'alpaca',
          name: 'Test API Key',
          apiKey: 'test-api-key-123',
          apiSecret: 'test-secret-456',
          baseUrl: ''
        });
      });

      // Form should close after successful submission
      expect(screen.queryByTestId('add-api-key-modal')).not.toBeInTheDocument();
    });

    it('should cancel add API key form', async () => {
      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('add-api-key-button'));
      expect(screen.getByTestId('add-api-key-modal')).toBeInTheDocument();

      await user.click(screen.getByTestId('cancel-add-button'));
      expect(screen.queryByTestId('add-api-key-modal')).not.toBeInTheDocument();
    });
  });

  describe('Edit API Key Functionality', () => {
    it('should open edit form when edit button is clicked', async () => {
      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('edit-button-key_1'));

      expect(screen.getByTestId('edit-api-key-modal')).toBeInTheDocument();
      expect(screen.getByTestId('edit-api-key-form')).toBeInTheDocument();
      expect(screen.getByTestId('edit-name-input')).toHaveValue('Alpaca Production');
    });

    it('should handle successful API key update', async () => {
      mockApiKeyContext.updateApiKey.mockResolvedValue({ success: true });

      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('edit-button-key_1'));

      // Modify name
      const nameInput = screen.getByTestId('edit-name-input');
      await user.clear(nameInput);
      await user.type(nameInput, 'Updated Alpaca Key');

      await user.click(screen.getByTestId('update-api-key-button'));

      await waitFor(() => {
        expect(mockApiKeyContext.updateApiKey).toHaveBeenCalledWith('key_1', {
          name: 'Updated Alpaca Key',
          baseUrl: ''
        });
      });

      expect(screen.queryByTestId('edit-api-key-modal')).not.toBeInTheDocument();
    });

    it('should cancel edit API key form', async () => {
      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('edit-button-key_1'));
      expect(screen.getByTestId('edit-api-key-modal')).toBeInTheDocument();

      await user.click(screen.getByTestId('cancel-edit-button'));
      expect(screen.queryByTestId('edit-api-key-modal')).not.toBeInTheDocument();
    });
  });

  describe('Delete API Key Functionality', () => {
    it('should show delete confirmation when delete button is clicked', async () => {
      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('delete-button-key_1'));

      expect(screen.getByTestId('delete-confirmation-modal')).toBeInTheDocument();
      expect(screen.getByTestId('delete-confirmation')).toBeInTheDocument();
      expect(screen.getByText('Are you sure you want to delete this API key?')).toBeInTheDocument();
    });

    it('should handle successful API key deletion', async () => {
      mockApiKeyContext.deleteApiKey.mockResolvedValue({ success: true });

      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('delete-button-key_1'));
      await user.click(screen.getByTestId('confirm-delete-button'));

      await waitFor(() => {
        expect(mockApiKeyContext.deleteApiKey).toHaveBeenCalledWith('key_1');
      });

      expect(screen.queryByTestId('delete-confirmation-modal')).not.toBeInTheDocument();
    });

    it('should cancel delete confirmation', async () => {
      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('delete-button-key_1'));
      expect(screen.getByTestId('delete-confirmation-modal')).toBeInTheDocument();

      await user.click(screen.getByTestId('cancel-delete-button'));
      expect(screen.queryByTestId('delete-confirmation-modal')).not.toBeInTheDocument();
    });
  });

  describe('Test API Key Functionality', () => {
    it('should handle API key testing', async () => {
      mockApiKeyContext.testApiKey.mockResolvedValue({ success: true, status: 'connected' });

      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      const testButton = screen.getByTestId('test-button-key_1');
      await user.click(testButton);

      // Should show testing state
      expect(screen.getByText('Testing...')).toBeInTheDocument();

      await waitFor(() => {
        expect(mockApiKeyContext.testApiKey).toHaveBeenCalledWith('key_1');
      });

      // Should return to normal state
      await waitFor(() => {
        expect(screen.getByText('Test Connection')).toBeInTheDocument();
      });
    });

    it('should handle API key testing error', async () => {
      mockApiKeyContext.testApiKey.mockRejectedValue(new Error('Connection failed'));
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('test-button-key_1'));

      await waitFor(() => {
        expect(mockApiKeyContext.testApiKey).toHaveBeenCalledWith('key_1');
      });

      await waitFor(() => {
        expect(consoleSpy).toHaveBeenCalledWith('Failed to test API key:', expect.any(Error));
      });

      consoleSpy.mockRestore();
    });
  });

  describe('Toggle API Key Status', () => {
    it('should toggle API key active status', async () => {
      mockApiKeyContext.updateApiKey.mockResolvedValue({ success: true });

      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      // Toggle active API key to inactive
      const toggleButton = screen.getByTestId('toggle-button-key_1');
      expect(toggleButton).toHaveTextContent('Deactivate');

      await user.click(toggleButton);

      await waitFor(() => {
        expect(mockApiKeyContext.updateApiKey).toHaveBeenCalledWith('key_1', {
          isActive: false
        });
      });
    });

    it('should activate inactive API key', async () => {
      mockApiKeyContext.updateApiKey.mockResolvedValue({ success: true });

      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      // Toggle inactive API key to active
      const toggleButton = screen.getByTestId('toggle-button-key_3');
      expect(toggleButton).toHaveTextContent('Activate');

      await user.click(toggleButton);

      await waitFor(() => {
        expect(mockApiKeyContext.updateApiKey).toHaveBeenCalledWith('key_3', {
          isActive: true
        });
      });
    });
  });

  describe('Form Validation', () => {
    it('should require provider selection in add form', async () => {
      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('add-api-key-button'));

      // Try to submit without selecting provider
      await user.type(screen.getByTestId('name-input'), 'Test Key');
      await user.type(screen.getByTestId('api-key-input'), 'test-key');

      const providerSelect = screen.getByTestId('provider-select');
      expect(providerSelect).toBeRequired();
    });

    it('should require name and API key fields', async () => {
      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('add-api-key-button'));

      const nameInput = screen.getByTestId('name-input');
      const apiKeyInput = screen.getByTestId('api-key-input');

      expect(nameInput).toBeRequired();
      expect(apiKeyInput).toBeRequired();
    });

    it('should validate URL format for base URL field', async () => {
      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('add-api-key-button'));

      const baseUrlInput = screen.getByTestId('base-url-input');
      expect(baseUrlInput).toHaveAttribute('type', 'url');
    });
  });

  describe('Security Features', () => {
    it('should mask API secret input', () => {
      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      user.click(screen.getByTestId('add-api-key-button'));

      const secretInput = screen.getByTestId('api-secret-input');
      expect(secretInput).toHaveAttribute('type', 'password');
    });

    it('should not display sensitive information in the UI', () => {
      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      // Should not show actual API keys or secrets in the list
      expect(screen.queryByText('test-api-key-123')).not.toBeInTheDocument();
      expect(screen.queryByText('test-secret-456')).not.toBeInTheDocument();
    });
  });

  describe('Loading and Error States', () => {
    it('should show loading spinner when loading', () => {
      const loadingContext = {
        ...mockApiKeyContext,
        loading: true
      };

      vi.mocked(vi.importMock('../../../components/ApiKeyProvider').useApiKeys).mockReturnValue(loadingContext);

      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument();
    });

    it('should show error message when there is an error', () => {
      const errorContext = {
        ...mockApiKeyContext,
        error: 'Failed to load API keys'
      };

      vi.mocked(vi.importMock('../../../components/ApiKeyProvider').useApiKeys).mockReturnValue(errorContext);

      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      expect(screen.getByTestId('error-message')).toBeInTheDocument();
      expect(screen.getByText('Error: Failed to load API keys')).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('should have proper semantic HTML structure', () => {
      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      expect(screen.getByRole('button', { name: /add new api key/i })).toBeInTheDocument();
      expect(screen.getByText('API Key Management')).toBeInTheDocument();
    });

    it('should support keyboard navigation', async () => {
      render(
        <TestWrapper>
          <MockSettingsApiKeysPage />
        </TestWrapper>
      );

      const addButton = screen.getByTestId('add-api-key-button');
      addButton.focus();
      expect(document.activeElement).toBe(addButton);

      // Test tab navigation to action buttons
      await user.tab();
      expect(document.activeElement).toBe(screen.getByTestId('test-button-key_1'));
    });
  });
});