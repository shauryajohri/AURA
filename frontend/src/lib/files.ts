import { api } from "../api";
import type { SavedItem } from "../types";

/** Files AURA reads into Saved Info when they're dropped or attached. Plain
 *  text and code still go inline into the message, as before — that's how
 *  you ask about a snippet — so only documents and images upload. */
export const SAVE_EXT = /\.(pdf|docx|png|jpe?g|webp|gif)$/i;
export const MAX_UPLOAD = 25 * 1024 * 1024;

export function isDocument(f: File): boolean {
  return SAVE_EXT.test(f.name) || f.type === "application/pdf" || f.type.startsWith("image/");
}

function toBase64(f: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      const s = String(r.result || "");
      resolve(s.slice(s.indexOf(",") + 1));
    };
    r.onerror = () => reject(r.error ?? new Error("couldn't read the file"));
    r.readAsDataURL(f);
  });
}

/** Upload one file to Saved Info. Throws with a sentence a person can act on. */
export async function uploadToSaved(f: File, origin = "upload"): Promise<SavedItem> {
  if (f.size > MAX_UPLOAD) throw new Error(`${f.name} is over 25 MB`);
  const data = await toBase64(f);
  const res = await api.uploadSaved(f.name, data, f.type, origin);
  if (!res.ok || !res.item) throw new Error(res.error || `couldn't save ${f.name}`);
  return res.item;
}
