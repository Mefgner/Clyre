export type MessageRole = 'user' | 'assistant' | 'thinking' | 'system'

export type StreamingEvents = 'user_message_insert' | 'context_window' | 'new_thinking_chunk' | 'new_chunk' | 'assistant_message_insert' | 'error' | 'done'

export interface ThreadMetadata {
  id: string
  title: string
  updateTime: string
  creationDate: string
}

export interface ThreadMessage {
  role: MessageRole
  content: string | null
  thinking?: string | null
  order?: number
}

export interface ThreadHistory extends ThreadMetadata {
  isGenerating?: boolean
  messages: ThreadMessage[]
}

export interface ContextWindowInfo {
  includedMessages: number
  omittedMessages: number
  firstIncludedOrder: number
  promptTokens: number
  slotTokens: number
  reservedOutputTokens: number
}

export interface ThreadStreamingPayload {
  chunk: string | null
  event: StreamingEvents
  threadId: string | null
  includedMessages?: number
  omittedMessages?: number
  firstIncludedOrder?: number
  promptTokens?: number
  slotTokens?: number
  reservedOutputTokens?: number
}

// PLAN-NOTE(fe-chat-cache): reserved for the upcoming chat-history caching layer.
// Intended shape: per-thread in-memory cache keyed by thread id, so switching
// threads does not refetch `GET /thread/{id}` every time (see stores/thread.ts
// header comment and PLAN.md §6.4). Not imported anywhere yet.
export interface ThreadHistoryCache {
  [id: string]: ThreadHistory
}
