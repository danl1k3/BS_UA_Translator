export const API_BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '');

// fetch до gateway; помилки HTTP перетворюються на Error з повідомленням сервера.
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === 'string' ? body.detail : `Server error (${response.status})`,
    );
  }
  return response;
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Unknown error';
}
