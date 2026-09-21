import { useMemo, useState } from 'react'
import './App.css'

const employeeRecords = {
  E001: { name: 'Priya Raman', department: 'Engineering', annual: 15, sick: 10, casual: 5 },
  E002: { name: 'Arjun Kumar', department: 'Marketing', annual: 0, sick: 12, casual: 3 },
  E003: { name: 'Divya Sekar', department: 'Sales', annual: 20, sick: 10, casual: 5 },
}

const holidayList = [
  '2026-01-26 • Republic Day',
  '2026-03-08 • Holi',
  '2026-08-15 • Independence Day',
  '2026-10-02 • Gandhi Jayanti',
  '2026-12-25 • Christmas',
]

const quickPrompts = [
  'What is my leave balance?',
  'List the holidays in 2026.',
  'Can I apply for 5 days annual leave?',
  'Apply for 3 days casual leave next week.',
]

function App() {
  const [employeeId, setEmployeeId] = useState('E001')
  const [question, setQuestion] = useState('What is my leave balance?')
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: 'Hello! I can check your leave balance, show public holidays, or help with a leave request.',
    },
  ])
  const [loading, setLoading] = useState(false)

  const employee = useMemo(() => employeeRecords[employeeId], [employeeId])

  function buildAssistantReply(input) {
    const clean = input.toLowerCase()

    if (clean.includes('balance') || clean.includes('leave')) {
      return `Your current leave balance is: ${employee.annual} annual days, ${employee.sick} sick days, and ${employee.casual} casual days remaining.`
    }

    if (clean.includes('holiday') || clean.includes('vacation') || clean.includes('day off')) {
      return `Upcoming public holidays: ${holidayList.join(' | ')}`
    }

    if (clean.includes('apply')) {
      if (employee.annual >= 5) {
        return `You have enough annual leave for 5 days. The desk agent would validate the dates and then apply the leave request.`
      }
      return `Your current annual leave is ${employee.annual} days, so a 5-day application would be rejected by policy.`
    }

    return 'I can help with leave balances, holiday calendars, or leave applications. Try one of the suggested prompts.'
  }

  function handleSubmit(event) {
    event.preventDefault()
    if (!question.trim()) return

    const nextUserMessage = { role: 'user', text: question.trim() }
    setMessages((prev) => [...prev, nextUserMessage])
    setLoading(true)

    window.setTimeout(() => {
      const reply = buildAssistantReply(question)
      setMessages((prev) => [...prev, { role: 'assistant', text: reply }])
      setLoading(false)
    }, 350)
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <p className="eyebrow">SoDak EduTech</p>
          <h1>Absence Assistant</h1>
        </div>

        <div className="employee-panel">
          <label htmlFor="employeeId">Employee</label>
          <div className="employee-select-wrap">
            <select id="employeeId" value={employeeId} onChange={(e) => setEmployeeId(e.target.value)}>
              {Object.entries(employeeRecords).map(([id, record]) => (
                <option key={id} value={id}>
                  {id} — {record.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="meta-box">
          <p><strong>Name:</strong> {employee.name}</p>
          <p><strong>Dept:</strong> {employee.department}</p>
        </div>
      </aside>

      <main className="main-panel">
        <header className="top-bar">
          <div>
            <p className="eyebrow">Leave dashboard</p>
            <h2>{employee.name}</h2>
          </div>
          <button type="button" className="ghost-button">Manager view</button>
        </header>

        <section className="chat-panel">
          <div className="chat-header">
            <h3>Chat</h3>
            <span className="status-pill">Online</span>
          </div>

          <div className="message-list">
            {messages.map((message, index) => (
              <div key={`${message.role}-${index}`} className={`message ${message.role}`}>
                <span className="message-role">{message.role === 'assistant' ? 'Assistant' : 'You'}</span>
                <p>{message.text}</p>
              </div>
            ))}
          </div>

          <div className="quick-prompts">
            {quickPrompts.map((prompt) => (
              <button key={prompt} type="button" onClick={() => setQuestion(prompt)}>
                {prompt}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="chat-form">
            <textarea
              rows="4"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask about leave balance, holidays, or an application..."
            />
            <div className="form-actions">
              <button type="submit" className="primary-button" disabled={loading}>
                {loading ? 'Thinking...' : 'Send'}
              </button>
            </div>
          </form>
        </section>
      </main>
    </div>
  )
}

export default App
