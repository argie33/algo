// Minimal test to check basic vitest functionality
import { describe, it, expect } from 'vitest';

describe('Minimal Test', () => {
  it('should pass a basic assertion', () => {
    expect(1 + 1).toBe(2);
  });

  it('should handle basic JavaScript', () => {
    const obj = { name: 'test' };
    expect(obj.name).toBe('test');
  });
});