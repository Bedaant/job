export type ControlSig = { tag: string; type: string; id: string; name: string };
export function relink(oldSigs: ControlSig[], freshSigs: ControlSig[]): number[];
