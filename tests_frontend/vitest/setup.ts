import { vi } from 'vitest'

// Vuetify display composable needs matchMedia; jsdom does not provide it.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

// v-textarea auto-grow observes sizes; jsdom has no ResizeObserver.
class NoopResizeObserver {
  observe () {}
  unobserve () {}
  disconnect () {}
}
vi.stubGlobal('ResizeObserver', NoopResizeObserver)
