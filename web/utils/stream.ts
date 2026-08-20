function parseString<T> (line: string) {
  try {
    return JSON.parse(line) as T
  } catch (error) {
    console.warn(`Failed to parse JSON line: ${line}`, error)
  }
}

export async function* readNDJSONStream<T> (body: string): AsyncGenerator<T> {
  if (!body) {
    throw new Error('Empty response')
  }

  const lines = body.split('\n')

  for (const line of lines) {
    const trimmedLine = line.trim()

    if (!trimmedLine) {
      continue
    }

    yield parseString<T>(trimmedLine) ?? {} as T
  }
}
