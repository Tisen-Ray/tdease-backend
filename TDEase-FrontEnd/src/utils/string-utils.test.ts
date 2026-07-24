import { describe, expect, it } from 'vitest'
import { sanitizeRunName, isValidRunName } from './string-utils'

describe('sanitizeRunName', () => {
  it('keeps allowed characters (word, . _ : - space)', () => {
    expect(sanitizeRunName('Soy Analysis v2.1_b1:c1-d1')).toBe('Soy Analysis v2.1_b1:c1-d1')
  })

  it('strips characters the backend rejects (slash, paren, question)', () => {
    // Backend SAFE_ID_RE = ^[\w._:\- ]{1,128}$ — slashes/parens/? would 400.
    expect(sanitizeRunName('Soy/Analysis (v2)?')).toBe('SoyAnalysis v2')
  })

  it('caps length at 128', () => {
    const long = 'a'.repeat(200)
    expect(sanitizeRunName(long).length).toBe(128)
  })

  it('falls back when the result would be empty', () => {
    expect(sanitizeRunName('///???', 'Untitled Run')).toBe('Untitled Run')
  })

  it('trims surrounding whitespace', () => {
    expect(sanitizeRunName('  Soy Run  ')).toBe('Soy Run')
  })
})

describe('isValidRunName', () => {
  it('accepts a clean name', () => {
    expect(isValidRunName('Soy Analysis v2')).toBe(true)
  })

  it('rejects slashes', () => {
    expect(isValidRunName('Soy/Analysis')).toBe(false)
  })

  it('rejects parentheses', () => {
    expect(isValidRunName('Soy (v2)')).toBe(false)
  })

  it('rejects empty', () => {
    expect(isValidRunName('')).toBe(false)
  })
})
