let onUnauthorized = () => {};
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}
export async function api(path, { token, ...options } = {}) {
  const response = await fetch("/api" + path, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...(options.body ? { body: JSON.stringify(options.body) } : {}),
  });
  if (response.status === 204) return null;
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && token) onUnauthorized(token);
    const detail = Array.isArray(data.detail)
      ? data.detail.map((e) => `${e.loc.at(-1)}: ${e.msg}`).join("; ")
      : data.detail;
    throw new Error(detail || "Unable to complete this request.");
  }
  return data;
}
