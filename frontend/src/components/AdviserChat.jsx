import Icon from './Icon';

const starterQuestions = [
  'What can I plant this month?',
  'How should I prepare my soil?',
  'How can I protect seedlings from heavy rain?',
];

export default function AdviserChat({
  messages, messageInput, chatLoading, chatError,
  onInputChange, onSend, onPresetQuestion,
}) {
  return (
    <section className="adviser-section" id="adviser">
      <div className="container adviser-layout">
        <div className="adviser-copy">
          <div className="eyebrow light"><span className="eyebrow-number">03</span> Ask your farming adviser</div>
          <h2>One good question<br />can change a season.</h2>
          <p>Chat with Nuru about crop choices, planting timing, soil care and weather preparation. It uses your field context only when you have connected it.</p>
          <div className="adviser-points">
            <span><Icon name="check" size={17} /> Plain-language guidance</span>
            <span><Icon name="check" size={17} /> Built for local decisions</span>
            <span><Icon name="check" size={17} /> Encourages expert advice when needed</span>
          </div>
        </div>
        <div className="chat-shell">
          <div className="chat-header">
            <div className="advisor-avatar"><Icon name="leaf" size={21} /></div>
            <div><strong>Nuru, your field adviser</strong><span><i /> Ready to help</span></div>
            <Icon name="spark" size={20} />
          </div>
          <div className="messages" aria-live="polite">
            {messages.map((m, i) => (
              <div className={`message ${m.role}${m.failed ? ' failed' : ''}`} key={`${m.role}-${i}`}>
                <span>{m.text}</span>
                {m.failed && <em className="message-flag">Not sent</em>}
              </div>
            ))}
            {chatLoading && <div className="message assistant typing"><span><i /><i /><i /></span></div>}
          </div>
          {messages.length < 3 && (
            <div className="starter-questions">
              {starterQuestions.map((q) => (
                <button type="button" key={q} onClick={() => onPresetQuestion(q)}>
                  {q} <Icon name="arrow" size={14} />
                </button>
              ))}
            </div>
          )}
          {chatError && <p className="form-error chat-error">{chatError}</p>}
          {/* The submit event used to be handed straight to onSend, which takes the
              message text — so every send called trim() on a FormEvent and threw
              unless a preset question supplied the text. */}
          <form
            className="chat-form"
            onSubmit={(event) => {
              event.preventDefault()
              onSend()
            }}
          >
            <input
              value={messageInput}
              onChange={(e) => onInputChange(e.target.value)}
              placeholder="Ask about your field…"
              aria-label="Ask Nuru a question"
            />
            <button type="submit" aria-label="Send question" disabled={!messageInput.trim() || chatLoading}>
              <Icon name="arrow" size={19} />
            </button>
          </form>
        </div>
      </div>
    </section>
  );
}