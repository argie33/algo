/**
 * Simple Unit Test to verify test environment setup
 */

import { describe, it, expect } from 'vitest'

describe('🧪 Basic Unit Test Environment', () => {
  it('should have localStorage available', () => {
    expect(localStorage).toBeDefined()
    expect(typeof localStorage.getItem).toBe('function')
    expect(typeof localStorage.setItem).toBe('function')
  })

  it('should have window object available', () => {
    expect(window).toBeDefined()
    expect(window.localStorage).toBeDefined()
  })

  it('should have document object available', () => {
    expect(document).toBeDefined()
  })

  it('should be able to use localStorage methods', () => {
    localStorage.setItem('test-key', 'test-value')
    expect(localStorage.getItem('test-key')).toBe('test-value')
    localStorage.removeItem('test-key')
    expect(localStorage.getItem('test-key')).toBeNull()
  })

  it('should have proper test environment variables', () => {
    expect(process.env.NODE_ENV).toBe('test')
    expect(process.env.VITE_API_URL).toBeDefined()
  })
})