import { useState } from 'react'
import { askChatbot } from '../api'

export default function Chatbot() {
  const [question, setQuestion] = useState('')
  const [thread, setThread] = useState([
    { role: 'system', text: 'Ask about any state, facility, or alert — e.g. "alerts in Jharkhand".' },
  ])
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!question.trim()) return
    const q = question
    setThread((t) => [...t, { role: 'user', text: q }])
    setQuestion('')
    setLoading(true)
    try {
      const res = await askChatbot(q)
      setThread((t) => [...t, { role: 'assistant', text: res.answer }])
    } catch (err) {
      setThread((t) => [...t, { role: 'assistant', text: 'Could not reach the backend — is it running?' }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="chatbot">
      <div className="chatbot__thread">
        {thread.map((m, i) => (
          <div key={i} className={`chatbot__msg chatbot__msg--${m.role}`}>{m.text}</div>
        ))}
        {loading && <div className="chatbot__msg chatbot__msg--assistant">…</div>}
      </div>
      <form className="chatbot__form" onSubmit={handleSubmit}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about a state or facility…"
        />
        <button type="submit">Ask</button>
      </form>
    </div>
  )
}
