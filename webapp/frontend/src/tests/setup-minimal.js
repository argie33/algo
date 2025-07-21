/**
 * Minimal Test Setup - for debugging hanging issues
 */

import { beforeAll, afterAll, beforeEach, afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import '@testing-library/jest-dom'

// Minimal test setup
beforeAll(() => {
  console.log('🧪 Minimal test environment setup...')
  process.env.NODE_ENV = 'test'
  console.log('✅ Minimal setup complete')
})

// Cleanup after each test
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

// Global teardown
afterAll(() => {
  console.log('🧹 Cleaning up test environment...')
})

export default {}