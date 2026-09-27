// Type contract for combobox.mjs (plain JS so node --test runs it unchanged).
export const COMBOBOX_MAX_WIDGETS: number;
export const COMBOBOX_WAIT_MS: number;
export const COMBOBOX_TYPE_WAIT_MS: number;
export const COMBOBOX_TOTAL_MS: number;

export interface ComboboxSnapshot {
  tag: string;
  role: string | null;
  visible: boolean;
  inReactSelect: boolean;
  ariaAutocomplete: string | null;
  ariaHaspopup: string | null;
  ariaControls: string | null;
}
export function comboboxKind(s: ComboboxSnapshot): "react-select" | "listbox" | null;
export function optionLabels(texts: (string | null | undefined)[]): string[];
export function matchOption(labels: string[], value: string): number;

export interface ReadOps {
  open(): Promise<unknown>;
  waitForOptions(): Promise<string[]>;
  close(): Promise<unknown>;
}
export function readOptions(ops: ReadOps): Promise<string[]>;
export function readAllOptions(
  widgets: ReadOps[],
  opts?: { now?: () => number; maxWidgets?: number; totalMs?: number },
): Promise<(string[] | null)[]>;

export interface FillOps<H> {
  displayed(): string;
  open(): Promise<unknown>;
  findOption(label: string): Promise<H | null>;
  canType: boolean;
  type(text: string): Promise<unknown>;
  click(option: H): Promise<unknown>;
  clear(): Promise<unknown>;
  close(): Promise<unknown>;
}
export function fillCombobox<H>(ops: FillOps<H>, label: string): Promise<boolean>;
