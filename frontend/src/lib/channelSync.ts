import { useEffect } from 'react';
import { apiFetch } from './api';
import { useAppStore, type RemoteChannelConversation } from './store';

const POLL_MS = 10_000;

/**
 * Keep phone (iMessage) conversations in the regular chat list.
 *
 * Polls the server's durable phone history and merges it into the normal
 * conversation store, so iMessage threads open in the same chat view with
 * the same components (only a badge marks the channel).
 */
export function useChannelConversationSync(): void {
  const sync = useAppStore((s) => s.syncChannelConversations);
  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const res = await apiFetch('/v1/channels/sendblue/conversations');
        if (!res.ok) return;
        const data = (await res.json()) as { conversations?: RemoteChannelConversation[] };
        if (active && Array.isArray(data.conversations)) sync(data.conversations);
      } catch {
        // Server offline: keep the last synced copy.
      }
    };
    void refresh();
    const timer = setInterval(refresh, POLL_MS);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [sync]);
}
