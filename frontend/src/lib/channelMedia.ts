import { getBase } from './api';

/** URL for a stored phone attachment (served by the local Jarvis server). */
export function channelMediaUrl(id: string): string {
  return `${getBase()}/v1/channels/sendblue/media/${encodeURIComponent(id)}`;
}
