import { Lang } from '../i18n/translations'

/**
 * Bridges the backend chat agent and the app's own pages.
 *
 * Two ways the assistant decides "the farmer wants page X":
 *
 * 1. INTENT_ROUTES — the backend's /api/ai/chat already classifies every
 *    message into an intent (see backend/app/ai/nlp.py INTENT_KEYWORDS /
 *    backend/app/agents/agent.py). We reuse that classification instead of
 *    re-detecting it, so "should I water my tomato today?" both gets
 *    answered AND offers to open the Water & Irrigation page.
 *
 * 2. matchPageCommand() — a small, offline, keyword-based matcher for
 *    explicit "open/go to <page>" requests. This covers pages that have no
 *    chat intent (Dashboard, Machinery, Analytics...) and — importantly —
 *    works instantly with no network round trip, which matters when a
 *    farmer is on a weak rural connection and just wants to switch screens.
 */

export const INTENT_ROUTES: Record<string, string> = {
  irrigation: '/water',
  weather: '/weather',
  soil: '/soil',
  disease: '/plant-health',
  pest_management: '/pest-management',
  scheme: '/schemes',
  fertilizer: '/market',
}

const INTENT_NAV_KEYS: Record<string, string> = {
  irrigation: 'nav.water',
  weather: 'nav.weather',
  soil: 'nav.soil',
  disease: 'nav.plant',
  pest_management: 'nav.pest',
  scheme: 'nav.schemes',
  fertilizer: 'nav.market',
}

export interface PageMatch {
  route: string
  /** i18n key for the page's own nav label, e.g. 'nav.water'. */
  navKey: string
}

/** Map a backend chat intent (e.g. "irrigation") to a page, if one exists. */
export function routeForIntent(intent?: string): PageMatch | null {
  if (!intent) return null
  const route = INTENT_ROUTES[intent]
  return route ? { route, navKey: INTENT_NAV_KEYS[intent] } : null
}

interface PageCommand {
  route: string
  navKey: string
  keywords: Partial<Record<Lang, string[]>>
}

// Pages a chat intent doesn't cover, matched directly by name/synonym.
const PAGE_COMMANDS: PageCommand[] = [
  { route: '/dashboard', navKey: 'nav.dashboard', keywords: {
    en: ['dashboard', 'home page', 'home screen', 'main page'],
    hi: ['डैशबोर्ड', 'होम पेज', 'मुख्य पेज'],
    ta: ['முகப்புப் பலகை', 'முகப்பு பக்கம்'] } },
  // "My Farm" and "Farm Setup" are now one page at /farm — a single entry
  // covers both sets of phrasing a farmer might use for it.
  { route: '/farm', navKey: 'nav.farm', keywords: {
    en: ['my farm', 'farm profile', 'my garden', 'farm setup', 'set up my farm'],
    hi: ['मेरा खेत', 'खेत प्रोफाइल', 'मेरा बगीचा', 'खेत सेटअप', 'खेत सेट अप'],
    ta: ['என் பண்ணை', 'பண்ணை விவரம்', 'என் தோட்டம்', 'பண்ணை அமைப்பு'] } },
  { route: '/soil', navKey: 'nav.soil', keywords: {
    en: ['soil health', 'soil page', 'soil test'],
    hi: ['मिट्टी स्वास्थ्य', 'मिट्टी पेज', 'मिट्टी जांच'],
    ta: ['மண் ஆரோக்கியம்', 'மண் பரிசோதனை', 'மண் பக்கம்'] } },
  { route: '/water', navKey: 'nav.water', keywords: {
    en: ['irrigation page', 'water page', 'watering'],
    hi: ['सिंचाई पेज', 'पानी पेज'],
    ta: ['பாசனம் பக்கம்', 'நீர் பக்கம்'] } },
  { route: '/plant-health', navKey: 'nav.plant', keywords: {
    en: ['plant health', 'check my plant', 'leaf photo'],
    hi: ['पौध स्वास्थ्य', 'पौधे की जांच', 'पत्ती फोटो'],
    ta: ['தாவர ஆரோக்கியம்', 'இலை புகைப்படம்'] } },
  { route: '/crop-advisor', navKey: 'nav.crop', keywords: {
    en: ['crop advisor', 'which crop should i grow', 'crop recommendation'],
    hi: ['फसल सलाहकार', 'कौन सी फसल उगाऊं', 'फसल सिफारिश'],
    ta: ['பயிர் ஆலோசகர்', 'எந்த பயிர் பயிரிடலாம்'] } },
  { route: '/market', navKey: 'nav.market', keywords: {
    en: ['market page', 'mandi price', 'crop price', 'fertilizer offers'],
    hi: ['बाज़ार पेज', 'मंडी भाव', 'फसल भाव', 'खाद ऑफर'],
    ta: ['சந்தை பக்கம்', 'சந்தை விலை', 'உர சலுகை'] } },
  { route: '/machinery', navKey: 'nav.machinery', keywords: {
    en: ['machinery', 'rent a tractor', 'equipment rental'],
    hi: ['मशीन किराया', 'ट्रैक्टर किराए', 'उपकरण किराया'],
    ta: ['இயந்திர வாடகை', 'டிராக்டர் வாடகை'] } },
  { route: '/pest-management', navKey: 'nav.pest', keywords: {
    en: ['pest management', 'pest page', 'insect problem'],
    hi: ['कीट प्रबंधन', 'कीट पेज'],
    ta: ['பூச்சி மேலாண்மை', 'பூச்சி பக்கம்'] } },
  { route: '/weather', navKey: 'nav.weather', keywords: {
    en: ['weather page', 'forecast'],
    hi: ['मौसम पेज', 'मौसम पूर्वानुमान'],
    ta: ['வானிலை பக்கம்', 'வானிலை முன்னறிவிப்பு'] } },
  { route: '/ai-advisor', navKey: 'nav.ai', keywords: {
    en: ['ai advisor page', 'chat page'],
    hi: ['एआई सलाहकार पेज', 'चैट पेज'],
    ta: ['ஏஐ ஆலோசகர் பக்கம்', 'அரட்டை பக்கம்'] } },
  { route: '/schemes', navKey: 'nav.schemes', keywords: {
    en: ['government scheme', 'schemes page', 'subsidy page'],
    hi: ['सरकारी योजना', 'योजना पेज', 'सब्सिडी पेज'],
    ta: ['அரசு திட்டங்கள்', 'திட்ட பக்கம்'] } },
  { route: '/alerts', navKey: 'nav.alerts', keywords: {
    en: ['alerts', 'notifications'],
    hi: ['चेतावनियां', 'सूचनाएं'],
    ta: ['எச்சரிக்கைகள்', 'அறிவிப்புகள்'] } },
  { route: '/analytics', navKey: 'nav.analytics', keywords: {
    en: ['analytics', 'sensor trends'],
    hi: ['विश्लेषण', 'सेंसर रुझान'],
    ta: ['பகுப்பாய்வு', 'சென்சார் போக்கு'] } },
  { route: '/settings', navKey: 'nav.settings', keywords: {
    en: ['settings', 'my account'],
    hi: ['सेटिंग्स', 'मेरा खाता'],
    ta: ['அமைப்புகள்', 'என் கணக்கு'] } },
]

// Verb phrases that turn a bare page name into a clear "take me there"
// command. Without one, a page keyword only counts as navigation if the
// whole message is short (a farmer just naming the page they want).
const NAV_VERBS: Partial<Record<Lang, string[]>> = {
  en: ['open', 'go to', 'show me', 'take me to', 'navigate to'],
  hi: ['खोलो', 'खोलें', 'ले चलो', 'ले चलिए', 'दिखाओ', 'दिखाइए', 'पर जाओ'],
  ta: ['திற', 'திறக்க', 'அழைத்துச் செல்', 'காட்டு', 'செல்ல'],
}

/**
 * Offline match for an explicit "open/go to <page>" command. Returns null
 * for anything that isn't clearly a navigation request, so ordinary
 * questions ("how much water does tomato need") fall through to the
 * backend chat agent instead of being hijacked into a page jump.
 */
export function matchPageCommand(text: string, lang: Lang): PageMatch | null {
  const t = text.toLowerCase().trim()
  if (!t) return null

  const verbs = NAV_VERBS[lang] || NAV_VERBS.en || []
  const hasVerb = verbs.some((v) => t.includes(v.toLowerCase()))
  const wordCount = t.split(/\s+/).filter(Boolean).length

  for (const cmd of PAGE_COMMANDS) {
    const kws = cmd.keywords[lang] || cmd.keywords.en || []
    const hit = kws.some((k) => t.includes(k.toLowerCase()))
    if (hit && (hasVerb || wordCount <= 4)) {
      return { route: cmd.route, navKey: cmd.navKey }
    }
  }
  return null
}
