import { useEffect, useState } from 'react';
import { apiFetch } from '../../lib/api';

type Conversation = { label: string; updated_at: string; messages: { role: string; content: string }[] };
export function PhoneConversations() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const response = await apiFetch('/v1/channels/sendblue/conversations');
        if (!response.ok) throw new Error('Cannot load phone conversations');
        const data = await response.json();
        if (active) { setConversations(data.conversations); setError(''); }
      } catch { if (active) setError('Phone conversations unavailable. Check the Jarvis connection.'); }
    };
    void refresh(); const timer = setInterval(refresh, 10000);
    return () => { active = false; clearInterval(timer); };
  }, []);
  return <section className="hud-panel p-5 mb-5" aria-label="iMessage conversations">
    <h2 className="text-base font-semibold mb-2">Your iMessage conversation with Jarvis</h2>
    <p className="text-xs mb-4" style={{ color: 'var(--color-text-secondary)' }}>Recent phone exchanges · refreshes every 10 seconds · stored replies do not confirm delivery</p>
    {error && <p role="alert">{error}</p>}
    {!error && !conversations.length && <p className="text-sm">Text Jarvis from your iPhone to start a conversation.</p>}
    {conversations.map((conversation, index) => <div key={index} className="mb-4">
      <p className="text-xs mb-2">{conversation.label} · updated {new Date(conversation.updated_at).toLocaleString()}</p>
      <div className="space-y-3 max-h-96 overflow-y-auto" aria-label={conversation.label}>
        {conversation.messages.map((message, i) => <div key={i} className="rounded-lg p-3" style={{ background: message.role === 'user' ? 'var(--color-bg-tertiary)' : 'var(--color-surface)' }}>
          <strong className="text-xs">{message.role === 'user' ? 'You · iMessage' : 'Jarvis'}</strong>
          <p className="text-sm whitespace-pre-wrap mt-1">{message.content}</p>
        </div>)}
        {conversation.messages[conversation.messages.length - 1]?.role === 'user' && <p className="text-xs">No reply stored yet. Jarvis may still be working.</p>}
      </div>
    </div>)}
    <p className="text-xs mt-2" style={{ color: 'var(--color-text-secondary)' }}>Shows the last 20 retained messages per conversation. Your imported Apple message history remains available for search.</p>
  </section>;
}
