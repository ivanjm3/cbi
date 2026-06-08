import { describe, it, expect } from 'vitest'

describe('Vitest Setup', () => {
  it('should run basic tests', () => {
    expect(1 + 1).toBe(2)
  })
  
  it('should have jest-dom matchers available', () => {
    const element = document.createElement('div')
    document.body.appendChild(element)
    expect(element).toBeInTheDocument()
    document.body.removeChild(element)
  })
})
