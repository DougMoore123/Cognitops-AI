// Base URL is injected at build time from the environment variable.
// Locally, Vite's proxy handles /api and /supervisor routes.
// In production (Static Web App), set VITE_API_BASE_URL to the APIM gateway URL.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: options?.body instanceof FormData
      ? undefined  // let browser set multipart boundary
      : { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status} ${res.statusText}: ${text}`)
  }

  return res.json() as Promise<T>
}

export const get  = <T>(path: string) => request<T>(path)
export const post = <T>(path: string, body: unknown | FormData) =>
  request<T>(path, {
    method: 'POST',
    body: body instanceof FormData ? body : JSON.stringify(body),
  })
