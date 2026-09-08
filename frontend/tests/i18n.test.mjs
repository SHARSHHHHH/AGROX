/**
 * Translation coverage check.
 *
 * Run with:  node tests/i18n.test.mjs
 *
 * Catches two failure modes that are easy to miss by eye:
 *   1. A key present in English but absent in Tamil or Hindi, which silently
 *      falls back to English and leaves the page half-translated.
 *   2. A hardcoded English string left in a page instead of a t() call.
 */
import fs from 'fs'
import path from 'path'

const SRC = path.join(process.cwd(), 'src')
let failures = 0
const fail = (m) => { console.error('  FAIL ' + m); failures++ }
const pass = (m) => console.log('  pass ' + m)

// ---------- 1. dictionary parity ----------
const dict = fs.readFileSync(path.join(SRC, 'i18n/translations.ts'), 'utf8')
const keysIn = (block) => [...block.matchAll(/^\s{4}'([^']+)':/gm)].map((m) => m[1])

const ui = dict.slice(dict.indexOf('export const UI'), dict.indexOf('export const VALUES'))
const en = keysIn(ui.slice(ui.indexOf('  en: {'), ui.indexOf('  ta: {')))
const ta = keysIn(ui.slice(ui.indexOf('  ta: {'), ui.indexOf('  hi: {')))
const hi = keysIn(ui.slice(ui.indexOf('  hi: {')))

console.log(`\nUI keys: en=${en.length} ta=${ta.length} hi=${hi.length}`)
const missTa = en.filter((k) => !ta.includes(k))
const missHi = en.filter((k) => !hi.includes(k))
missTa.length ? fail(`${missTa.length} keys missing in Tamil: ${missTa.slice(0, 5)}`)
              : pass('every English UI key exists in Tamil')
missHi.length ? fail(`${missHi.length} keys missing in Hindi: ${missHi.slice(0, 5)}`)
              : pass('every English UI key exists in Hindi')

// ---------- 2. data values parity ----------
const vals = dict.slice(dict.indexOf('export const VALUES'))
const kv = (b) => [...b.matchAll(/'([^']+)':\s*'/g)].map((m) => m[1])
const vTa = kv(vals.slice(vals.indexOf('  ta: {'), vals.indexOf('  hi: {')))
const vHi = kv(vals.slice(vals.indexOf('  hi: {')))
console.log(`VALUE keys: ta=${vTa.length} hi=${vHi.length}`)
const vMiss = vTa.filter((k) => !vHi.includes(k))
vMiss.length ? fail(`values missing in Hindi: ${vMiss.slice(0, 5)}`)
             : pass('data values match across Tamil and Hindi')

// ---------- 3. Hindi must be complete (priority language) ----------
const hiBlock = ui.slice(ui.indexOf('  hi: {'))
const emptyHi = [...hiBlock.matchAll(/^\s{4}'([^']+)':\s*''/gm)].map((m) => m[1])
emptyHi.length ? fail(`empty Hindi strings: ${emptyHi}`)
               : pass('no empty Hindi strings')

// ---------- 4. no hardcoded English left in pages ----------
// Placeholders showing example values are intentionally not translated.
const SKIP = /^(OFF|ON|N|P|K|pH|AI|IPM|LOW|HIGH|Chrome|Edge|Madhya Pradesh|Indore|Tomato|Mahindra 575 DI, 47 HP)$/
const dirs = ['pages', 'layouts', 'components']
let hardcoded = []
for (const d of dirs) {
  for (const f of fs.readdirSync(path.join(SRC, d)).filter((x) => x.endsWith('.tsx'))) {
    const body = fs.readFileSync(path.join(SRC, d, f), 'utf8')
    const found = new Set()
    for (const m of body.matchAll(/>\s*([A-Z][a-zA-Z][a-zA-Z ,&/?.'-]{4,60}?)\s*</g)) {
      const txt = m[1].trim()
      if (!SKIP.test(txt) && !txt.includes('{')) found.add(txt)
    }
    for (const m of body.matchAll(/(?:placeholder|label)="([A-Z][^"]{4,60})"/g)) {
      if (!SKIP.test(m[1])) found.add(m[1])
    }
    if (found.size) hardcoded.push(`${d}/${f}: ${[...found].slice(0, 3).join(' | ')}`)
  }
}
hardcoded.length ? fail(`hardcoded English found:\n     ${hardcoded.join('\n     ')}`)
                 : pass('no hardcoded English strings in pages')

console.log(failures === 0 ? '\nAll i18n checks passed.\n'
                           : `\n${failures} i18n check(s) FAILED.\n`)
process.exit(failures === 0 ? 0 : 1)
