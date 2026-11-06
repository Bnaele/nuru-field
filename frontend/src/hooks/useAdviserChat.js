// The AI adviser conversation.
//
// Moved out of App.jsx. Two bugs went with it:
//
// 1. sendMessage read `messages` from the enclosing render. Two messages sent
//    before a re-render both saw the same history, so the model lost the turn in
//    between. History is now taken from a functional update.
// 2. A failed send removed the user's message with `slice(0, -1)`, which deleted
//    the wrong entry if anything else had been appended. The message is now kept
//    and marked, so the grower can retry instead of retyping.

import { useCallback, useRef, useState } from 'react'
import { api } from '../lib/api'

const GREETING =
  'Hello, I am Nuru. I can help you plan, observe and respond to the conditions in your field. What are you growing?'

// The API sends history in its own shape; the UI keeps a flat list.
function asHistory(messages) {
  return messages
    .filter((message) => message.text && !message.failed)
    .slice(-6)
    .map((message) => ({ role: message.role, text: message.text }))
}

export function useAdviserChat({ getFieldContext }) {
  // A ref mirrors the list so `send` can read the real history without depending
  // on a render having happened. Reading state from the closure of `send` was the
  // original bug: two quick messages both saw the same history.
  const messagesRef = useRef([{ role: 'assistant', text: GREETING }])
  const [messages, setMessages] = useState(messagesRef.current)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const loadingRef = useRef(false)

  const push = useCallback((next) => {
    messagesRef.current = [...messagesRef.current, next]
    setMessages(messagesRef.current)
  }, [])

  const send = useCallback(
    async (text) => {
      const trimmed = (text ?? input).trim()
      if (!trimmed || loadingRef.current) return

      loadingRef.current = true
      setInput('')
      setError('')
      setLoading(true)

      const history = asHistory(messagesRef.current)
      push({ role: 'user', text: trimmed })

      try {
        const response = await api.askAdviser({
          message: trimmed,
          history,
          fieldContext: getFieldContext?.() || 'No field context has been shared yet.',
        })
        push({
          role: 'assistant',
          text: response?.answer || 'No answer came back. Please try again.',
        })
      } catch (chatError) {
        setError(chatError.message)
        // Keep the question visible and flagged rather than deleting it, so the
        // grower can retry without retyping.
        messagesRef.current = messagesRef.current.map((message, index) =>
          index === messagesRef.current.length - 1 ? { ...message, failed: true } : message,
        )
        setMessages(messagesRef.current)
      } finally {
        loadingRef.current = false
        setLoading(false)
      }
    },
    [getFieldContext, input, push],
  )

  return { messages, input, setInput, loading, error, send }
}
