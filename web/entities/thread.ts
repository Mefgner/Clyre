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

// PLAN-NOTE(fe-chat-cache): reserved for the upcoming chat-history caching layer.
// Intended shape: per-thread in-memory cache keyed by thread id, so switching
// threads does not refetch `GET /thread/{id}` every time (see stores/thread.ts
// header comment and PLAN.md §6.4). Not imported anywhere yet.
export interface ThreadHistoryCache {
  [id: string]: ThreadHistory
}
