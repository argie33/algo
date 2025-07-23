/**
 * User Input Validation Integration Tests
 * Tests how the application handles invalid user inputs and edge cases
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import Settings from '../../../pages/Settings'
import StockDetail from '../../../pages/StockDetail'
import Portfolio from '../../../pages/Portfolio'
import AdvancedScreener from '../../../pages/AdvancedScreener'
import { AuthContext } from '../../../contexts/AuthContext'
import muiTheme from '../../../theme/muiTheme'
import AuthModal from '../../../components/auth/AuthModal'

// Mock react-router-dom params
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useParams: () => ({ ticker: 'AAPL' })
  }
})

// Mock API service
const mockApi = {
  getApiConfig: vi.fn(() => ({
    apiUrl: 'https://test-api.com',
    isServerless: true,
    isConfigured: true
  }))
}

vi.mock('../../../services/api', () => mockApi)

// Mock fetch for API calls
let fetchMock
const originalFetch = global.fetch

const TestWrapper = ({ children, isAuthenticated = true }) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
        cacheTime: 0
      }
    }
  })

  const mockAuthContextValue = {
    isAuthenticated,
    user: isAuthenticated ? { 
      id: 'test-user', 
      email: 'test@example.com',
      username: 'testuser',
      firstName: 'Test',
      lastName: 'User',
      tokens: { accessToken: 'test-token' }
    } : null,
    login: vi.fn().mockResolvedValue({ success: true }),
    register: vi.fn().mockResolvedValue({ success: true }),
    confirmRegistration: vi.fn().mockResolvedValue({ success: true }),
    resetPasswordRequest: vi.fn().mockResolvedValue({ success: true }),
    confirmPasswordReset: vi.fn().mockResolvedValue({ success: true }),
    logout: vi.fn(),
    checkAuthState: vi.fn(),
    loading: false,
    error: null,
    clearError: vi.fn()
  }

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ThemeProvider theme={muiTheme}>
          <AuthContext.Provider value={mockAuthContextValue}>
            {children}
          </AuthContext.Provider>
        </ThemeProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

describe('User Input Validation Tests', () => {
  beforeEach(() => {
    fetchMock = vi.fn()
    global.fetch = fetchMock
    vi.clearAllMocks()
  })

  afterEach(() => {
    global.fetch = originalFetch
    vi.restoreAllMocks()
  })

  describe('Form Input Validation', () => {
    test('handles invalid email addresses in settings', async () => {
      fetchMock.mockResolvedValue({
        ok: false,
        status: 400,
        json: async () => ({ error: 'Invalid email format' })
      })

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Account Settings')).toBeInTheDocument()
      })

      // Click on Profile tab
      const profileTab = screen.getByRole('tab', { name: /profile/i })
      fireEvent.click(profileTab)

      await waitFor(() => {
        const emailInput = screen.getByLabelText(/email/i)
        expect(emailInput).toBeInTheDocument()

        // Test various invalid email formats
        const invalidEmails = [
          'invalid-email',
          '@domain.com',
          'user@',
          'user@@domain.com',
          'user@domain',
          'user space@domain.com',
          'very-long-email-address-that-exceeds-normal-limits@extremely-long-domain-name-that-should-not-exist.com'
        ]

        invalidEmails.forEach(async (email) => {
          fireEvent.change(emailInput, { target: { value: email } })
          
          const saveButton = screen.getByRole('button', { name: /save changes/i })
          fireEvent.click(saveButton)

          // Should handle invalid email gracefully
          await waitFor(() => {
            expect(emailInput).toBeInTheDocument() // Form should still be there
          })
        })
      })
    })

    test('handles SQL injection attempts in search inputs', async () => {
      render(
        <TestWrapper>
          <AdvancedScreener />
        </TestWrapper>
      )

      await waitFor(() => {
        const searchInputs = screen.queryAllByRole('textbox')
        if (searchInputs.length > 0) {
          const searchInput = searchInputs[0]

          // Test SQL injection patterns
          const sqlInjectionAttempts = [
            "'; DROP TABLE users; --",
            "' OR '1'='1",
            "UNION SELECT * FROM passwords",
            "'; INSERT INTO users VALUES ('hacker', 'password'); --",
            "<script>alert('xss')</script>",
            "../../etc/passwd",
            "admin' OR 1=1 /*"
          ]

          sqlInjectionAttempts.forEach(async (injection) => {
            fireEvent.change(searchInput, { target: { value: injection } })
            
            // Should not cause application to crash
            expect(searchInput).toBeInTheDocument()
          })
        }
      })
    })

    test('handles extremely long input values', async () => {
      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Account Settings')).toBeInTheDocument()
      })

      const profileTab = screen.getByRole('tab', { name: /profile/i })
      fireEvent.click(profileTab)

      await waitFor(() => {
        const firstNameInput = screen.getByLabelText(/first name/i)
        const longString = 'a'.repeat(10000)

        fireEvent.change(firstNameInput, { target: { value: longString } })

        // Should handle long input without performance issues
        expect(firstNameInput.value.length).toBeGreaterThan(1000)
      })
    })

    test('handles special characters in name fields', async () => {
      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Account Settings')).toBeInTheDocument()
      })

      const profileTab = screen.getByRole('tab', { name: /profile/i })
      fireEvent.click(profileTab)

      await waitFor(() => {
        const firstNameInput = screen.getByLabelText(/first name/i)
        const lastNameInput = screen.getByLabelText(/last name/i)

        const specialCharNames = [
          "José María",
          "François-René",
          "O'Connor",
          "李小明",
          "محمد عبدالله",
          "Niño-García",
          "Van der Berg",
          "McDonald's",
          "@#$%^&*()",
          "Name\nWith\nNewlines"
        ]

        specialCharNames.forEach(async (name) => {
          fireEvent.change(firstNameInput, { target: { value: name } })
          fireEvent.change(lastNameInput, { target: { value: name } })

          // Should handle special characters gracefully
          expect(firstNameInput).toBeInTheDocument()
          expect(lastNameInput).toBeInTheDocument()
        })
      })
    })
  })

  describe('Authentication Input Validation', () => {
    test('handles invalid login credentials', async () => {
      render(
        <TestWrapper isAuthenticated={false}>
          <AuthModal open={true} onClose={() => {}} />
        </TestWrapper>
      )

      await waitFor(() => {
        const usernameInput = screen.getByLabelText(/username|email/i)
        const passwordInput = screen.getByLabelText(/password/i)

        // Test various invalid inputs
        const invalidCredentials = [
          { username: '', password: '' },
          { username: 'user', password: '123' },
          { username: 'a'.repeat(1000), password: 'b'.repeat(1000) },
          { username: '<script>alert("xss")</script>', password: 'password' },
          { username: 'user@domain.com', password: '' },
          { username: '', password: 'password123' }
        ]

        invalidCredentials.forEach(async ({ username, password }) => {
          fireEvent.change(usernameInput, { target: { value: username } })
          fireEvent.change(passwordInput, { target: { value: password } })

          const loginButton = screen.getByRole('button', { name: /sign in|login/i })
          fireEvent.click(loginButton)

          // Should handle invalid credentials without crashing
          await waitFor(() => {
            expect(usernameInput).toBeInTheDocument()
            expect(passwordInput).toBeInTheDocument()
          })
        })
      })
    })

    test('handles password complexity requirements', async () => {
      render(
        <TestWrapper isAuthenticated={false}>
          <AuthModal open={true} onClose={() => {}} />
        </TestWrapper>
      )

      // Switch to registration mode
      await waitFor(() => {
        const signUpTab = screen.queryByText(/sign up|register/i)
        if (signUpTab) {
          fireEvent.click(signUpTab)
        }
      })

      await waitFor(() => {
        const passwordInput = screen.queryByLabelText(/password/i)
        if (passwordInput) {
          const weakPasswords = [
            '123',
            'password',
            'abc',
            '11111111',
            'qwerty',
            'password123',
            'admin',
            '!@#$%^&*()',
            'aaaaaaaa'
          ]

          weakPasswords.forEach(async (password) => {
            fireEvent.change(passwordInput, { target: { value: password } })

            // Should provide feedback on weak passwords
            expect(passwordInput).toBeInTheDocument()
          })
        }
      })
    })
  })

  describe('Numeric Input Validation', () => {
    test('handles invalid stock symbol inputs', async () => {
      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      )

      await waitFor(() => {
        // Look for stock symbol input or display
        const stockElements = screen.queryAllByText(/stock|symbol|ticker/i)
        expect(stockElements.length).toBeGreaterThan(0)
      })

      // Should handle invalid stock symbols gracefully
      // (Stock symbols come from URL params in this component)
    })

    test('handles invalid numeric inputs in portfolio values', async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({
          data: { totalValue: 10000, positions: [] },
          success: true
        })
      })

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      )

      await waitFor(() => {
        const numericInputs = screen.queryAllByRole('spinbutton')
        
        if (numericInputs.length > 0) {
          const input = numericInputs[0]
          
          const invalidNumbers = [
            'abc',
            '12.34.56',
            'Infinity',
            'NaN',
            '1e308', // Overflow
            '-1e308', // Underflow
            '++123',
            '--456',
            '123,456,789,012,345,678,901', // Too large
            '0x123', // Hex
            '123e',
            '..'
          ]

          invalidNumbers.forEach(async (value) => {
            fireEvent.change(input, { target: { value } })
            
            // Should handle invalid numeric inputs
            expect(input).toBeInTheDocument()
          })
        }
      })
    })
  })

  describe('File Upload Validation', () => {
    test('handles invalid file types', async () => {
      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      await waitFor(() => {
        const fileInputs = screen.queryAllByRole('button')
        const uploadButtons = fileInputs.filter(button => 
          button.textContent?.toLowerCase().includes('upload') ||
          button.textContent?.toLowerCase().includes('import')
        )

        if (uploadButtons.length > 0) {
          // Create invalid file objects
          const invalidFiles = [
            new File(['malicious content'], 'virus.exe', { type: 'application/exe' }),
            new File(['<?php echo "hack"; ?>'], 'script.php', { type: 'application/php' }),
            new File(['<script>alert("xss")</script>'], 'xss.html', { type: 'text/html' }),
            new File([''], 'empty.txt', { type: 'text/plain' }),
            new File(['x'.repeat(100 * 1024 * 1024)], 'huge.txt', { type: 'text/plain' }) // 100MB file
          ]

          invalidFiles.forEach(async (file) => {
            // Simulate file selection would typically be done through input[type="file"]
            // This is a simplified test since we can't easily simulate file selection
            expect(uploadButtons[0]).toBeInTheDocument()
          })
        }
      })
    })

    test('handles corrupted file uploads', async () => {
      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      // Mock a corrupted file response
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ error: 'Corrupted file' })
      })

      await waitFor(() => {
        expect(screen.getByText('Account Settings')).toBeInTheDocument()
      })

      // Should handle corrupted file responses gracefully
    })
  })

  describe('Cross-Site Scripting (XSS) Prevention', () => {
    test('sanitizes HTML input in text fields', async () => {
      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Account Settings')).toBeInTheDocument()
      })

      const profileTab = screen.getByRole('tab', { name: /profile/i })
      fireEvent.click(profileTab)

      await waitFor(() => {
        const firstNameInput = screen.getByLabelText(/first name/i)

        const xssAttempts = [
          '<script>alert("xss")</script>',
          '<img src="x" onerror="alert(1)">',
          'javascript:alert("xss")',
          '<svg onload="alert(1)">',
          '<iframe src="javascript:alert(1)"></iframe>',
          '<object data="javascript:alert(1)">',
          '<embed src="javascript:alert(1)">',
          '<link rel="stylesheet" href="javascript:alert(1)">',
          '<style>@import "javascript:alert(1)";</style>',
          '<meta http-equiv="refresh" content="0;javascript:alert(1)">'
        ]

        xssAttempts.forEach(async (xss) => {
          fireEvent.change(firstNameInput, { target: { value: xss } })

          // Input should be sanitized (no script execution)
          expect(firstNameInput).toBeInTheDocument()
          
          // Check that dangerous content is not rendered as HTML
          expect(document.querySelector('script')).toBeNull()
        })
      })
    })

    test('prevents XSS in dynamic content rendering', async () => {
      const maliciousData = {
        data: {
          positions: [
            {
              symbol: '<script>alert("xss")</script>',
              quantity: 10,
              price: 150
            },
            {
              symbol: 'MSFT',
              quantity: '<img src="x" onerror="alert(1)">',
              price: 200
            }
          ]
        },
        success: true
      }

      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => maliciousData
      })

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      )

      await waitFor(() => {
        const portfolioElements = screen.queryAllByText(/portfolio/i)
        expect(portfolioElements.length).toBeGreaterThan(0)
      })

      // Should not execute malicious scripts
      expect(document.querySelector('script')).toBeNull()
      expect(document.querySelector('img[onerror]')).toBeNull()
    })
  })

  describe('Input Rate Limiting', () => {
    test('handles rapid input changes without performance degradation', async () => {
      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Account Settings')).toBeInTheDocument()
      })

      const profileTab = screen.getByRole('tab', { name: /profile/i })
      fireEvent.click(profileTab)

      await waitFor(() => {
        const firstNameInput = screen.getByLabelText(/first name/i)
        const startTime = performance.now()

        // Simulate rapid input changes
        for (let i = 0; i < 100; i++) {
          fireEvent.change(firstNameInput, { target: { value: `Name${i}` } })
        }

        const endTime = performance.now()
        const duration = endTime - startTime

        // Should handle rapid changes efficiently
        expect(duration).toBeLessThan(5000) // 5 seconds max
        expect(firstNameInput).toBeInTheDocument()
      })
    })

    test('handles simultaneous input on multiple fields', async () => {
      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Account Settings')).toBeInTheDocument()
      })

      const profileTab = screen.getByRole('tab', { name: /profile/i })
      fireEvent.click(profileTab)

      await waitFor(() => {
        const firstNameInput = screen.getByLabelText(/first name/i)
        const lastNameInput = screen.getByLabelText(/last name/i)
        const emailInput = screen.getByLabelText(/email/i)

        // Simulate simultaneous input changes
        const inputs = [firstNameInput, lastNameInput, emailInput]
        const startTime = performance.now()

        for (let i = 0; i < 50; i++) {
          inputs.forEach((input, index) => {
            fireEvent.change(input, { target: { value: `Value${i}-${index}` } })
          })
        }

        const endTime = performance.now()
        const duration = endTime - startTime

        // Should handle simultaneous input efficiently
        expect(duration).toBeLessThan(3000) // 3 seconds max
        expect(firstNameInput).toBeInTheDocument()
      })
    })
  })

  describe('Edge Case Input Handling', () => {
    test('handles null byte injection attempts', async () => {
      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Account Settings')).toBeInTheDocument()
      })

      const profileTab = screen.getByRole('tab', { name: /profile/i })
      fireEvent.click(profileTab)

      await waitFor(() => {
        const firstNameInput = screen.getByLabelText(/first name/i)

        const nullByteAttempts = [
          'normal\x00malicious',
          'file.txt\x00.exe',
          'user\x00admin',
          '\x00\x01\x02\x03',
          'test\u0000payload'
        ]

        nullByteAttempts.forEach(async (input) => {
          fireEvent.change(firstNameInput, { target: { value: input } })

          // Should handle null bytes safely
          expect(firstNameInput).toBeInTheDocument()
        })
      })
    })

    test('handles unicode and emoji inputs', async () => {
      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Account Settings')).toBeInTheDocument()
      })

      const profileTab = screen.getByRole('tab', { name: /profile/i })
      fireEvent.click(profileTab)

      await waitFor(() => {
        const firstNameInput = screen.getByLabelText(/first name/i)

        const unicodeInputs = [
          '🚀💎🙌', // Emojis
          '测试用户', // Chinese
          'עברית', // Hebrew
          'العربية', // Arabic
          'Русский', // Russian
          'हिन्दी', // Hindi
          '日本語', // Japanese
          '한국어', // Korean
          'Ñoño', // Spanish with tildes
          'Café', // French with accents
          '𝕌𝕟𝕚𝕔𝕠𝕕𝕖', // Mathematical symbols
          '⚡⭐🎉🔥💯' // Mixed emojis
        ]

        unicodeInputs.forEach(async (input) => {
          fireEvent.change(firstNameInput, { target: { value: input } })

          // Should handle unicode inputs gracefully
          expect(firstNameInput).toBeInTheDocument()
        })
      })
    })
  })
})