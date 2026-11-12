/**
 * Role groups for the demo, a copy of backend/applications/role_groups.py and
 * backend/classifier/role_quality.py. The place list is only the places the demo data uses; role_synonyms.json
 * and role_words.json are copies of the files in backend/constants (a test checks they match).
 */
import synonymsFile from './role_synonyms.json';
import wordsFile from './role_words.json';

export const NO_ROLE_LABEL = 'Role not found';

const ANYWHERE = new Set([
  'junior', 'jr', 'jnr', 'senior', 'sr', 'snr', 'regular', 'mid level', 'midlevel', 'mid senior', 'entry level',
  'intern', 'internship', 'working student', 'trainee', 'graduate', 'grad', 'apprentice', 'apprenticeship',
  'full time', 'fulltime', 'part time', 'parttime', 'remote', 'fully remote', 'hybrid', 'on site', 'onsite',
  'mlodszy', 'mlodsza', 'starszy', 'starsza', 'stazysta', 'stazystka', 'praktykant', 'praktykantka', 'staz',
  'praktyki', 'samodzielny', 'samodzielna', 'zdalnie', 'zdalna', 'zdalny', 'hybrydowo', 'hybrydowa',
  'hybrydowy', 'stacjonarnie', 'pelny etat',
  'praktikant', 'praktikantin', 'praktikum', 'werkstudent', 'werkstudentin', 'auszubildender', 'auszubildende',
  'azubi', 'duales studium', 'vollzeit', 'teilzeit', 'home office', 'homeoffice', 'mobiles arbeiten',
  'stagiaire', 'alternant', 'alternante', 'alternance', 'teletravail', 'becario', 'becaria', 'practicas', 'remoto',
]);
const PLACES = new Set([
  'berlin', 'hamburg', 'munich', 'cologne', 'frankfurt', 'amsterdam', 'london', 'warsaw', 'krakow', 'eu',
  'europe', 'emea', 'germany', 'netherlands', 'poland', 'remote', 'hybrid',
]);
const LEADING = new Set(['lead', 'principal', 'mid', 'leitender', 'leitende']);
const TRAILING = new Set(['i', 'ii', 'iii', 'iv', 'l1', 'l2', 'l3', 'l4', 'level 1', 'level 2', 'level 3', 'level 4']);
const CONNECTORS = new Set(['in', 'at', 'w', 'we', 'im', 'en', 'a', 'for', 'and', 'und', 'oraz', '&', '@', '/', '+', '-']);

const LETTER = /[\p{L}]/u;
const DASHES = /[‐-―−]/gu;
const BRACKETS = /\([^)]*(?:\)|$)|\[[^\]]*(?:\]|$)|\{[^}]*(?:\}|$)/gu;
const GENDER =
  /(?<![\p{L}\p{N}_/])[mwfhk]\s*\/\s*[mwfhk](?:\s*\/\s*(?:d|div|divers|x|i))?(?![\p{L}\p{N}_/])|(?<![\p{L}\p{N}_])(?:all genders|alle geschlechter)(?![\p{L}\p{N}_])/giu;
const GENDER_SUFFIX = /(?<=\p{L})(?:[*:_]innen|[*:_]in|\s*\/\s*-?(?:in|innen|a|ka|ini))(?![\p{L}\p{N}_])/giu;
const JOB_ID =
  /#\s*[\p{L}\p{N}_-]+|(?<![\p{L}\p{N}_])(?:req|ref|job\s*id|id|nr|no)(?![\p{L}\p{N}_])\.?\s*[:#]?\s*[a-z]{0,4}[-_]?\d[\p{L}\p{N}_-]*|(?<![\p{L}\p{N}_])[a-z]{0,5}[-_]?\d{3,}[\p{L}\p{N}_-]*|(?<![\p{L}\p{N}_])\d+\s*%/giu;
const SEPARATORS = /\s+-\s+|\s*\|\s*|\s*,\s*|\s+@\s+/u;
const TOKEN = /[^\s\-/]+/gu;
const ENDS = ' .:;-/&*_+@';

export function fold(text: string): string {
  return (text || '')
    .toLowerCase()
    .replace(/ł/g, 'l')
    .normalize('NFKD')
    .replace(/\p{M}/gu, '')
    .replace(/-/g, ' ')
    .split(/\s+/)
    .filter(Boolean)
    .join(' ');
}

const plain = (word: string) => fold(word).replace(/[^\p{L}\p{N}_+#&]/gu, '');

// Is this text a job title at all? (role_quality.py)
const TYPE_WORDS = new Set(wordsFile.type_words);
const GENERIC_WORDS = new Set(wordsFile.generic_words);
const TITLE_WORDS = new Set(wordsFile.title_words);
const NOT_TITLES = new Set(wordsFile.not_titles);
const SENTENCE_WORDS = new Set(wordsFile.sentence_words);
const MAX_TITLE_WORDS = 8;
const EDGE = ' \t:;,.!?-–—|*"\'“”„';
const LABEL_SEP = String.raw`(?:\s*[:.\-–—|]\s*|\s+)`;
const LEADING_LABELS = [
  new RegExp(String.raw`^(?:the\s+|a\s+|an\s+)?(?:position|role|job|vacancy|stelle|poste|puesto)\s+(?:of|as|for|als|de)\b` + LABEL_SEP, 'i'),
  new RegExp(String.raw`^(?:the\s+)?(?:position|role|stanowisko)\b` + LABEL_SEP, 'i'),
  /^(?:job|vacancy|programme|program)\s*[:\-–—|]\s*/i,
  /^(?:programme|program)\s+(?=\S+\s+\S)/i,
];
const QUALITY_SEPARATORS = /\s+[-–—]\s+|\s*\|\s*|\s*,\s*|\s+@\s+/u;
const QUALITY_BRACKETS = /\([^)]*(?:\)|$)|\[[^\]]*(?:\]|$)|\{[^}]*(?:\}|$)/gu;

function stripEdges(text: string): string {
  let start = 0;
  let end = text.length;
  while (start < end && EDGE.includes(text[start] ?? '')) start += 1;
  while (end > start && EDGE.includes(text[end - 1] ?? '')) end -= 1;
  return text.slice(start, end);
}

const titleWords = (text: string) =>
  fold(text)
    .replace(/\//g, ' ')
    .split(' ')
    .map((w) => w.replace(/[^\p{L}\p{N}_+#&]/gu, ''))
    .filter(Boolean);

export function tidyRole(text: string | null | undefined): string {
  let out = stripEdges((text ?? '').replace(/_/g, ' / ').split(/\s+/).filter(Boolean).join(' '));
  for (let changed = true; changed; ) {
    changed = false;
    for (const label of LEADING_LABELS) {
      const rest = stripEdges(out.replace(label, ''));
      if (rest && rest !== out) {
        out = rest;
        changed = true;
      }
    }
  }
  return out;
}

function isTitleWord(word: string): boolean {
  if (TITLE_WORDS.has(word)) return true;
  if (NOT_TITLES.has(word) || GENERIC_WORDS.has(word) || word.length < 5) return false;
  return wordsFile.title_endings.some((ending) => word.endsWith(ending));
}

function allIn(words: string[], sets: Set<string>[]): boolean {
  for (let i = 0; i < words.length; ) {
    const size = matches(words, i, sets);
    if (!size) return false;
    i += size;
  }
  return true;
}

const hasSentenceWords = (text: string) => titleWords(text).some((w) => SENTENCE_WORDS.has(w));

function isTypeOnly(text: string): boolean {
  const words = titleWords(text);
  return words.length > 0 && allIn(words, [TYPE_WORDS, PLACES]);
}

function isGenericOnly(text: string): boolean {
  const words = titleWords(text);
  return (
    words.length > 0 &&
    !words.some(isTitleWord) &&
    words.every((w) => GENERIC_WORDS.has(w) || PLACES.has(w) || wordsFile.generic_endings.some((e) => w.endsWith(e)))
  );
}

function lacksTitleWord(text: string): boolean {
  const words = titleWords(text);
  return words.length > 3 && !words.some(isTitleWord);
}

function isCompany(text: string, company: string | null | undefined): boolean {
  if (!company || ['', 'unknown'].includes(fold(company))) return false;
  return titleWords(text).join(' ') === titleWords(company).join(' ');
}

function typedInBrackets(text: string): boolean {
  return [...text.matchAll(QUALITY_BRACKETS)].some((m) => isTypeOnly(m[0].slice(1).replace(/[)\]}]+$/, '')));
}

function pickRolePart(parts: string[], company?: string | null, typed = false): string | null {
  for (const raw of parts) {
    const part = tidyRole(raw);
    if (!part || !LETTER.test(part)) continue;
    if (isTypeOnly(part)) typed = true;
    else if (isCompany(part, company) || titleWords(part).length > MAX_TITLE_WORDS || lacksTitleWord(part)) continue;
    else if (!isGenericOnly(part) || typed) return part;
  }
  return null;
}

/** A sentence, the company's name, a department or kind of position alone, or a long phrase without a title word. */
export function notARole(text: string | null | undefined, company?: string | null): boolean {
  const role = tidyRole(text);
  if (!role || ['unknown', 'n/a', 'none'].includes(fold(role))) return true;
  if (hasSentenceWords(role) || isCompany(role, company)) return true;
  return pickRolePart(role.replace(QUALITY_BRACKETS, ' ').split(QUALITY_SEPARATORS), company, typedInBrackets(role)) === null;
}

function matches(words: string[], start: number, phrases: Set<string>[]): number {
  for (const size of [3, 2, 1]) {
    if (start + size > words.length) continue;
    const phrase = words.slice(start, start + size).join(' ');
    if (phrases.some((set) => set.has(phrase))) return size;
  }
  return 0;
}

function trimEnds(text: string): string {
  let out = text.split(/\s+/).filter(Boolean).join(' ');
  while (out && ENDS.includes(out[0] ?? '')) out = out.slice(1);
  while (out && ENDS.includes(out.at(-1) ?? '')) out = out.slice(0, -1);
  return out.trim();
}

function stripWords(text: string): string {
  const tokens = [...text.matchAll(TOKEN)];
  const words = tokens.map((t) => plain(t[0]));
  const keep = tokens.map((t, i) => Boolean(words[i]) || t[0] === '&' || t[0] === '+');
  for (let i = 0; i < words.length; ) {
    const size = matches(words, i, [ANYWHERE, PLACES]);
    if (size) {
      for (let j = i; j < i + size; j++) keep[j] = false;
      i += size;
    } else i += 1;
  }
  const kept = () => keep.flatMap((k, i) => (k ? [i] : []));
  const isConnector = (i: number) => CONNECTORS.has(words[i] ?? '') || CONNECTORS.has(tokens[i]?.[0] ?? '');
  for (let left = kept(); left.length > 1; left = kept()) {
    const first = left[0] ?? 0;
    if (LEADING.has(words[first] ?? '') && !(words[first] === 'mid' && words[first + 1] === 'market')) keep[first] = false;
    else if (isConnector(first)) keep[first] = false;
    else break;
  }
  for (let left = kept(); left.length > 1; left = kept()) {
    const last = left.at(-1) ?? 0;
    const before = left.at(-2) ?? 0;
    if (TRAILING.has(`${words[before]} ${words[last]}`)) keep[before] = keep[last] = false;
    else if (TRAILING.has(words[last] ?? '') || isConnector(last)) keep[last] = false;
    else break;
  }
  let out = '';
  let previousEnd: number | null = null;
  for (const index of kept()) {
    const token = tokens[index];
    if (!token) continue;
    const start = token.index ?? 0;
    if (previousEnd !== null) {
      const gap = text.slice(previousEnd, start);
      out += gap.includes('/') ? '/' : gap.trim() === '-' ? '-' : ' ';
    }
    out += token[0];
    previousEnd = start + token[0].length;
  }
  return out;
}

const capitalised = (text: string) => (text === text.toLowerCase() ? text[0]?.toUpperCase() + text.slice(1) : text);

function coreOf(text: string): string | null {
  const alternatives = text.split(/\s+\/\s+/).map((part) => trimEnds(stripWords(part))).filter(Boolean);
  if (alternatives.length > 1 && new Set(alternatives.map(groupKey)).size === 1) return alternatives[0] ?? null;
  const core = trimEnds(stripWords(text));
  return core && LETTER.test(core) ? core : null;
}

export function coreTitle(role: string | null | undefined, company?: string | null): string | null {
  let text = tidyRole(role);
  if (!text || ['unknown', 'n/a', 'none'].includes(fold(text))) return null;
  if (hasSentenceWords(text) || isCompany(text, company)) return null;
  text = text.replace(DASHES, '-');
  const typed = typedInBrackets(text);
  text = text.replace(BRACKETS, ' ').replace(GENDER, ' ').replace(GENDER_SUFFIX, '').replace(JOB_ID, ' ');
  const part = pickRolePart(text.split(SEPARATORS).map(trimEnds), company, typed);
  const core = part ? coreOf(part) : null;
  return core ? capitalised(core) : null;
}

const foldKey = (text: string) =>
  fold(text).replace(/\//g, ' ').replace(/[^\p{L}\p{N}_+#& ]/gu, ' ').split(/\s+/).filter(Boolean).join(' ');

const SYNONYMS = new Map<string, string>();
for (const [language, entries] of Object.entries(synonymsFile)) {
  if (language.startsWith('_') || typeof entries !== 'object') continue;
  for (const [variant, spelling] of Object.entries(entries as Record<string, string>)) {
    const from = foldKey(variant);
    const to = foldKey(spelling);
    if (from && from !== to) SYNONYMS.set(from, to);
  }
}
const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const SYNONYM_PATTERN = new RegExp(
  `(?<!\\S)(?:${[...SYNONYMS.keys()].sort((a, b) => b.length - a.length).map(escape).join('|')})(?!\\S)`,
  'gu',
);

export function groupKey(text: string | null | undefined): string | null {
  if (!text) return null;
  const key = foldKey(text).replace(SYNONYM_PATTERN, (match) => SYNONYMS.get(match) ?? match);
  return key.split(/\s+/).filter(Boolean).join(' ') || null;
}

export const roleGroup = (role: string | null | undefined, company?: string | null) => groupKey(coreTitle(role, company));

export function resolve(key: string | null, merges: Map<string, string>): string | null {
  const seen = new Set<string>();
  while (key !== null && merges.has(key) && !seen.has(key)) {
    seen.add(key);
    key = merges.get(key) ?? key;
  }
  return key;
}

export function effectiveGroup(
  role: string | null,
  override: string | null | undefined,
  merges: Map<string, string>,
  company?: string | null,
) {
  const own = override ? groupKey(override) : null;
  return resolve(own ?? roleGroup(role, company), merges);
}

export function groupLabels(
  entries: { role: string | null; company?: string | null; role_group_override?: string | null }[],
): Map<string, string> {
  const counts = new Map<string, Map<string, number>>();
  for (const { role, company, role_group_override: override } of entries) {
    for (const title of [coreTitle(role, company), override ? override.split(/\s+/).filter(Boolean).join(' ') : null]) {
      const key = title ? groupKey(title) : null;
      if (!title || !key) continue;
      const byTitle = counts.get(key) ?? new Map<string, number>();
      byTitle.set(title, (byTitle.get(title) ?? 0) + 1);
      counts.set(key, byTitle);
    }
  }
  const labels = new Map<string, string>();
  for (const [key, byTitle] of counts) {
    let best = '';
    let most = 0;
    for (const [title, count] of byTitle) if (count > most) [best, most] = [title, count];
    labels.set(key, best);
  }
  return labels;
}

export function labelFor(key: string | null, labels: Map<string, string>): string {
  if (key === null) return NO_ROLE_LABEL;
  return labels.get(key) ?? key.charAt(0).toUpperCase() + key.slice(1);
}
