import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

class MemoryStorage {
  private store = new Map<string, string>();
  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
  removeItem(key: string): void {
    this.store.delete(key);
  }
}

describe('syncChannelConversations', () => {
  beforeEach(() => {
    vi.resetModules();
    (globalThis as unknown as { localStorage: MemoryStorage }).localStorage = new MemoryStorage();
  });
  afterEach(() => {
    (globalThis as unknown as { localStorage?: MemoryStorage }).localStorage = undefined;
  });

  const remote = [
    {
      id: 'sendblue-abc',
      channel: 'sendblue',
      created_at: '2026-11-18T06:00:00Z',
      updated_at: '2026-11-18T06:01:00Z',
      messages: [
        { id: 'sendblue-abc-1', role: 'user', content: 'hey', created_at: '2026-11-18T06:00:00Z', attachments: [{ id: 'p.jpg', type: 'image/jpeg', kind: 'image' as const }] },
        { id: 'sendblue-abc-2', role: 'assistant', content: 'sup', agent: 'Jarvis', model: 'qwen3.5:9b', delivery_status: 'DELIVERED', created_at: '2026-11-18T06:01:00Z' },
      ],
    },
  ];

  it('puts phone threads in the regular chat list and keeps desktop messages', async () => {
    const { useAppStore } = await import('./store');
    const s = useAppStore.getState();
    s.syncChannelConversations(remote);
    let conv = useAppStore.getState().conversations.find((c) => c.id === 'sendblue-abc')!;
    expect(conv.channel).toBe('imessage');
    expect(conv.messages.map((m) => m.content)).toEqual(['hey', 'sup']);
    expect(conv.messages[0].attachments?.[0].id).toBe('p.jpg');
    expect(conv.messages[1]).toMatchObject({ agent: 'Jarvis', model: 'qwen3.5:9b', deliveryStatus: 'DELIVERED' });

    // A message typed on the desktop into this thread survives the next sync.
    s.addMessage('sendblue-abc', { id: 'local-1', role: 'user', content: 'from desktop', timestamp: Date.parse('2026-11-18T06:02:00Z') });
    s.syncChannelConversations(remote);
    conv = useAppStore.getState().conversations.find((c) => c.id === 'sendblue-abc')!;
    expect(conv.messages.map((m) => m.content)).toEqual(['hey', 'sup', 'from desktop']);
  });
});
