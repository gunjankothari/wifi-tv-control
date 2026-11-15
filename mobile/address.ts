// The helper's phone listener uses the same port as its local API (TVD_PORT, default 8765).
export const DEFAULT_PORT = 8765;

/**
 * Turns what the user typed ("192.168.1.20", "192.168.1.20:8765", "http://192.168.1.20:8765/")
 * into the helper's page URL, or null when it isn't a usable address.
 */
export function helperUrl(input: string): string | null {
  const text = input.trim();
  if (!text) return null;
  const withScheme = /^https?:\/\//i.test(text) ? text : `http://${text}`;
  const match = /^(https?):\/\/([a-z0-9.-]+|\[[0-9a-f:]+\])(?::(\d{1,5}))?\/?$/i.exec(withScheme);
  if (!match) return null;
  const [, scheme, host, port] = match;
  if (port !== undefined && (Number(port) < 1 || Number(port) > 65535)) return null;
  return `${scheme.toLowerCase()}://${host.toLowerCase()}:${port ?? DEFAULT_PORT}/`;
}
