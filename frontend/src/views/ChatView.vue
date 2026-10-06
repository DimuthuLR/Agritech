<script setup lang="ts">
import { ref, nextTick, onMounted, computed } from 'vue'
import { Send, Bot, User, Loader2, Sparkles } from 'lucide-vue-next'
import { usePlotsStore } from '../stores/plots'
import { chatApi, type ChatMessage } from '../api/chat'

const plotsStore = usePlotsStore()

const messages = ref<ChatMessage[]>([])
const input = ref('')
const selectedPlotId = ref<string>('')
const sending = ref(false)
const error = ref<string | null>(null)

const messagesEl = ref<HTMLElement | null>(null)
const inputEl = ref<HTMLTextAreaElement | null>(null)

const hasMessages = computed(() => messages.value.length > 0)

const suggestions = [
  'Should I irrigate today?',
  'What was decided for this plot last week?',
  'Is the weather favorable for spraying?',
  'How much have I spent on this plot?',
]

onMounted(async () => {
  if (plotsStore.plots.length === 0) {
    await plotsStore.fetchAll()
  }
  if (plotsStore.plots.length > 0) {
    selectedPlotId.value = plotsStore.plots[0].id
  }
  inputEl.value?.focus()
})

async function scrollToBottom() {
  await nextTick()
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  }
}

async function send(text?: string) {
  const message = (text ?? input.value).trim()
  if (!message || sending.value) return

  error.value = null
  messages.value.push({ role: 'user', content: message })
  input.value = ''
  sending.value = true
  await scrollToBottom()

  try {
    const response = await chatApi.send({
      message,
      plot_id: selectedPlotId.value || null,
      history: messages.value.slice(-11, -1),
    })
    messages.value.push({ role: 'assistant', content: response })
  } catch (e: any) {
    error.value =
      e?.response?.data?.detail || 'Assistant unavailable. Please try again.'
  } finally {
    sending.value = false
    await scrollToBottom()
    inputEl.value?.focus()
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

function clearChat() {
  messages.value = []
  error.value = null
}
</script>

<template>
  <div class="max-w-3xl mx-auto flex flex-col h-[calc(100vh-8rem)]">

    <!-- Header -->
    <div class="flex items-start justify-between gap-4 mb-4">
      <div>
        <h1 class="text-2xl font-semibold">Assistant</h1>
        <p class="text-muted text-sm mt-1">
          Ask about your farm — the assistant uses your live data.
        </p>
      </div>

      <div class="flex items-center gap-2">
        <select
          v-model="selectedPlotId"
          class="input text-sm py-1.5 max-w-[180px]"
        >
          <option value="">No plot context</option>
          <option v-if="plotsStore.loading" disabled value="__loading">
            Loading plots…
          </option>
          <option
            v-for="p in plotsStore.plots"
            :key="p.id"
            :value="p.id"
          >
            {{ p.name }}
          </option>
        </select>

        <button
          v-if="hasMessages"
          class="btn-ghost text-xs py-1.5 px-2"
          @click="clearChat"
        >
          Clear
        </button>
      </div>
    </div>

    <!-- Messages scroll area -->
    <div
      ref="messagesEl"
      class="flex-1 overflow-y-auto px-1 space-y-4"
    >
      <!-- ============================================================
           Empty state — shown only when there are no messages
           ============================================================ -->
      <div
        v-if="!hasMessages"
        class="flex flex-col items-center justify-center text-center py-16"
      >
        <div
          class="w-14 h-14 rounded-full bg-accent-soft text-accent
                 flex items-center justify-center mb-4"
        >
          <Sparkles :size="26" :stroke-width="1.75" />
        </div>

        <h2 class="text-lg font-medium">Ask me anything about your farm</h2>
        <p class="text-muted text-sm mt-2 max-w-sm">
          I can see your sensors, weather, recent decisions, and costs.
          Try one of these:
        </p>

        <div class="flex flex-wrap gap-2 mt-5 justify-center max-w-md">
          <button
            v-for="s in suggestions"
            :key="s"
            :disabled="!selectedPlotId"
            :class="[
              'px-3 py-1.5 rounded-full border border-border text-xs transition-colors',
              selectedPlotId
                ? 'text-muted hover:text-text hover:bg-card-hover'
                : 'text-muted/40 cursor-not-allowed',
            ]"
            @click="selectedPlotId && send(s)"
          >
            {{ s }}
          </button>
        </div>

        <p
          v-if="!selectedPlotId"
          class="text-xs text-warning mt-5 max-w-sm"
        >
          Select a plot above for sensor and weather answers.
          General knowledge questions work either way.
        </p>
      </div>

      <!-- ============================================================
           Message list — shown only when there are messages
           ============================================================ -->
      <template v-else>
        <div
          v-for="(m, i) in messages"
          :key="i"
          :class="[
            'flex gap-3',
            m.role === 'user' ? 'justify-end' : '',
          ]"
        >
          <!-- Assistant avatar -->
          <div
            v-if="m.role === 'assistant'"
            class="w-8 h-8 rounded-full bg-accent-soft text-accent
                   flex items-center justify-center shrink-0"
          >
            <Bot :size="16" :stroke-width="1.75" />
          </div>

          <!-- Bubble -->
          <div
            :class="[
              'max-w-[80%] rounded-lg px-4 py-2.5 text-sm leading-relaxed',
              m.role === 'user'
                ? 'bg-accent text-invert'
                : 'bg-card border border-border',
            ]"
          >
            <p class="whitespace-pre-wrap">{{ m.content }}</p>
          </div>

          <!-- User avatar -->
          <div
            v-if="m.role === 'user'"
            class="w-8 h-8 rounded-full bg-card border border-border
                   flex items-center justify-center shrink-0"
          >
            <User :size="16" :stroke-width="1.75" class="text-muted" />
          </div>
        </div>

        <!-- Typing indicator -->
        <div v-if="sending" class="flex gap-3">
          <div
            class="w-8 h-8 rounded-full bg-accent-soft text-accent
                   flex items-center justify-center shrink-0"
          >
            <Bot :size="16" :stroke-width="1.75" />
          </div>
          <div class="bg-card border border-border rounded-lg px-4 py-2.5">
            <div class="flex items-center gap-2 text-sm text-muted">
              <Loader2 :size="14" :stroke-width="2" class="animate-spin" />
              Thinking…
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- Error -->
    <div
      v-if="error"
      class="mt-3 text-sm text-danger bg-danger/10 rounded-sm px-3 py-2"
    >
      {{ error }}
    </div>

    <!-- Input -->
    <div class="mt-4">
      <div
        class="flex items-end gap-2 bg-card border border-border
               rounded-lg p-2 focus-within:border-accent"
      >
        <textarea
          ref="inputEl"
          v-model="input"
          rows="1"
          class="flex-1 bg-transparent resize-none outline-none
                 text-sm text-text placeholder:text-muted px-2 py-1.5
                 max-h-32"
          placeholder="Ask about your farm…"
          :disabled="sending"
          @keydown="onKeydown"
          @input="
            (e) => {
              const t = e.target as HTMLTextAreaElement
              t.style.height = 'auto'
              t.style.height = Math.min(t.scrollHeight, 128) + 'px'
            }
          "
        />
        <button
          class="btn-primary p-2"
          :disabled="sending || !input.trim()"
          @click="send()"
          aria-label="Send"
        >
          <Send :size="16" :stroke-width="2" />
        </button>
      </div>
      <p class="text-xs text-muted mt-2 text-center">
        The assistant cannot execute actions. To approve tasks, use the
        <router-link to="/tasks" class="text-accent hover:underline">Tasks</router-link>
        page.
      </p>
    </div>

  </div>
</template>