// The CV the site shows: what the admin saved, else the defaults in cv.js.
import * as defaults from './cv.js';
import { settings } from './db.js';
import { CV_SCHEMA } from '../public/js/cv-schema.js';

const MAX = { text: 300, url: 500, long: 3000 };
const LIST_MAX = 60;

export const cvDefaults = () => structuredClone(Object.fromEntries(CV_SCHEMA.map(s => [s.key, defaults[s.key]])));

// Keep only what the schema knows, as trimmed strings. Bad urls become empty.
function clean(field, v) {
  switch (field.type) {
    case 'text': case 'long': return typeof v === 'string' ? v.trim().slice(0, MAX[field.type]) : '';
    case 'url': {
      const s = typeof v === 'string' ? v.trim().slice(0, MAX.url) : '';
      return /^(https?:\/\/|mailto:|\/)/i.test(s) ? s : '';
    }
    case 'lines': return (Array.isArray(v) ? v : []).filter(x => typeof x === 'string').map(x => x.trim().slice(0, MAX.long)).filter(Boolean).slice(0, LIST_MAX);
    case 'object': return Object.fromEntries(field.fields.map(f => [f.key, clean(f, v?.[f.key])]));
    case 'list': return (Array.isArray(v) ? v : []).slice(0, LIST_MAX).map(x => clean({ type: 'object', fields: field.fields }, x));
  }
}

export const cleanCv = data => Object.fromEntries(CV_SCHEMA.map(s => [s.key, clean(s, data?.[s.key])]));

export function getCv() {
  const saved = settings.get('cv');
  const base = cvDefaults();
  if (!saved) return base;
  // sections missing from the save (new in the schema) fall back to cv.js
  return Object.fromEntries(CV_SCHEMA.map(s => [s.key, s.key in saved.value ? saved.value[s.key] : base[s.key]]));
}
export const cvMeta = () => ({ updated_at: settings.get('cv')?.updated_at || null });
export const saveCv = data => settings.set('cv', cleanCv(data));
export const resetCv = () => settings.remove('cv');
