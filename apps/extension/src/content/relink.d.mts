export type ControlSig = { tag: string; type: string; id: string; name: string };
export const READ_LIVE_TRIES: number;
export function readLive<T>(read: () => Promise<T>, stale: (out: T) => boolean): Promise<T>;
export function relink(oldSigs: ControlSig[], freshSigs: ControlSig[]): number[];
