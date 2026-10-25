import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

// jsdom has no IntersectionObserver (used by the reveal-on-scroll hook).
class NoopIntersectionObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.IntersectionObserver ??= NoopIntersectionObserver
