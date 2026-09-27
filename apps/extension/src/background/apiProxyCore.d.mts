export function allowedRoute(
  method: unknown,
  path: unknown,
): { method: string; pattern: RegExp; response: "json" | "bytes" } | null;
export function bytesToBase64(bytes: Uint8Array): string;
export function base64ToBytes(base64: string): Uint8Array<ArrayBuffer>;
