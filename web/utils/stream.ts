import { logger } from '@/utils/logger.ts'

function parseLine<T> (line: string): T | null {
  try {
    return JSON.parse(line) as T
  } catch (error) {
    logger.warn('ndjson_parse_failed', { line: line.slice(0, 200), error: String(error) })
    return null
  }
}

export async function* readNDJSONStream<T> (body: ReadableStream<Uint8Array>): AsyncGenerator<T> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) {
        break
      }

      buffer += decoder.decode(value, { stream: true })

      let newlineIndex = buffer.indexOf('\n')
      while (newlineIndex !== -1) {
        const line = buffer.slice(0, newlineIndex).trim()
        buffer = buffer.slice(newlineIndex + 1)

        if (line) {
          const parsed = parseLine<T>(line)
          if (parsed !== null) {
            yield parsed
          }
        }

        newlineIndex = buffer.indexOf('\n')
      }
    }

    const tail = (buffer + decoder.decode()).trim()
    if (tail) {
      const parsed = parseLine<T>(tail)
      if (parsed !== null) {
        yield parsed
      }
    }
  } finally {
    // Cancel the body on any early exit (consumer throw, break): without it
    // the socket stays open and the server-side generation runs to completion
    // into the void. On natural completion cancel() is a no-op.
    await reader.cancel().catch(() => {})
  }
}
