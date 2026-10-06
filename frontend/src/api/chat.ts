import { api } from './client'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatRequest {
  message: string
  plot_id?: string | null
  history: ChatMessage[]
}

export interface ChatResponse {
  response: string
}

export const chatApi = {
  async send(req: ChatRequest): Promise<string> {
    const { data } = await api.post<ChatResponse>('/chat/message', req, {
      // Qwen's first call loads the model into VRAM — up to 30s
      timeout: 90000,
    })
    return data.response
  },
}