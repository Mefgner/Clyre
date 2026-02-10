const unpackBody = (response: any) => response.body

function parseString<T> (line: string) {
  try {
    return JSON.parse(line) as T
  } catch (error) {
    console.warn(`Failed to parse JSON line: ${line}`, error)
  }
}

export async function* readNDJSONStream<T> (response: any): AsyncGenerator<T> {
  const body = unpackBody(response)

  if (!body) {
    throw new Error('Empty response')
  }

  const reader = body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()

      if (done) {
        break
      }

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')

      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmedLine = line.trim()

        if (!trimmedLine) {
          continue
        }

        yield parseString<T>(trimmedLine) ?? {} as T
      }
    }

    if (buffer.trim() !== '' && !buffer.endsWith('\n') && !buffer.endsWith('\r\n') && !buffer.endsWith('\r')) {
      yield parseString<T>(buffer) ?? {} as T
    }
  } finally {
    reader.releaseLock()
  }
}
