export type MessageRole = 'user' | 'assistant' | 'thinking' | 'system'

export type StreamingEvents = 'user_message_insert' | 'assistant_message_insert' | 'new_chunk' | 'done' // | 'error'

export interface ThreadMetadata {
  id: string
  title: string
  updateTime: string
  creationDate: string
}

export interface ThreadMessage {
  role: MessageRole
  content: string
  // citations?: Array<{
  //   sourceId: string
  //   text: string
  // }>
  // mode?: 'Quality' | 'Speed'
}

export interface ThreadHistory extends ThreadMetadata {
  messages: ThreadMessage[]
}

export interface ThreadStreamingPayload {
  chunk: string | null
  event: StreamingEvents
  threadId: string | null
}

export interface ThreadHistoryCache {
  [id: string]: ThreadHistory
}
