import { describe, it, expect } from 'vitest';

describe('Simple Test Suite', () => {
  it('basic math works', () => {
    expect(2 + 2).toBe(4);
  });

  it('strings concatenate', () => {
    expect('hello' + ' ' + 'world').toBe('hello world');
  });

  it('arrays have length', () => {
    expect([1, 2, 3].length).toBe(3);
  });
});
