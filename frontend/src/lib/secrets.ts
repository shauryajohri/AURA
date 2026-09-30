// Client-side mirror of core/integrations.find_keys, only for DISPLAY: the
// bubble you see after pasting a key shows "gsk_…Wx9Q", never the key. The
// server does the real masking before anything is stored or logged.
const PATTERNS: RegExp[] = [
  /sk-or-(?:v1-)?[A-Za-z0-9]{20,}/g,
  /sk-ant-[A-Za-z0-9_-]{20,}/g,
  /sk-(?:proj|svcacct|admin)-[A-Za-z0-9_-]{20,}/g,
  /(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{32,}/g,
  /gsk_[A-Za-z0-9]{20,}/g,
  /AIza[0-9A-Za-z_-]{30,}/g,
  /(?<![A-Za-z0-9])hf_[A-Za-z0-9]{20,}/g,
  /csk-[A-Za-z0-9]{20,}/g,
  /xai-[A-Za-z0-9]{20,}/g,
  /(?<![A-Za-z0-9])fw_[A-Za-z0-9]{16,}/g,
  /nvapi-[A-Za-z0-9_-]{20,}/g,
  /github_pat_[A-Za-z0-9_]{30,}/g,
  /(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{30,}/g,
  /tvly-[A-Za-z0-9_-]{16,}/g,
  /tgp_v1_[A-Za-z0-9_-]{20,}/g,
  /pplx-[A-Za-z0-9]{20,}/g,
  /(?<![A-Za-z0-9])BSA[A-Za-z0-9_-]{20,}/g,
];

export function maskKey(key: string): string {
  return key.length <= 10 ? key.slice(0, 2) + "…" : `${key.slice(0, 4)}…${key.slice(-4)}`;
}

export function maskSecrets(text: string): string {
  let out = text;
  for (const rx of PATTERNS) out = out.replace(rx, (k) => maskKey(k));
  return out;
}
