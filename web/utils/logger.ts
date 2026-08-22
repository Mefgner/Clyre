const PREFIX = '[clyre]'

function emit (method: 'debug' | 'info' | 'warn' | 'error', event: string, data?: Record<string, unknown>) {
  // Chatty diagnostics (prompt lengths, chunk metrics) stay in dev builds only.
  if ((method === 'debug' || method === 'info') && !import.meta.env.DEV) {
    return { event, ...data }
  }
  const line = { event, ...data }
  if (data === undefined) {
    console[method](PREFIX, event)
  } else {
    console[method](PREFIX, event, JSON.stringify(data))
  }
  return line
}

export const logger = {
  debug: (event: string, data?: Record<string, unknown>) => emit('debug', event, data),
  info: (event: string, data?: Record<string, unknown>) => emit('info', event, data),
  warn: (event: string, data?: Record<string, unknown>) => emit('warn', event, data),
  error: (event: string, data?: Record<string, unknown>) => emit('error', event, data),
}
