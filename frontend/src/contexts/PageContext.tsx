import { createContext, useContext, useRef, useState, ReactNode } from 'react'

/**
 * Lets whatever page is currently on screen publish a short, plain-text
 * summary of what it's actually showing right now — the same numbers
 * already rendered, not a re-fetch. The floating AI advisor reads this so
 * "what is happening here?" gets a real, page-specific answer everywhere in
 * the app, not a generic one.
 *
 * A page calls usePageContext().publish(pageName, summary) once its data has
 * loaded (and again whenever that data changes). The advisor only ever sees
 * the freshest published summary; nothing is cached across navigations.
 */

interface PageContextValue {
  pageName: string
  summary: string
}

interface PageContextApi extends PageContextValue {
  publish: (pageName: string, summary: string) => void
}

const Ctx = createContext<PageContextApi>({
  pageName: '', summary: '', publish: () => {},
})

export function PageContextProvider({ children }: { children: ReactNode }) {
  const [value, setValue] = useState<PageContextValue>({ pageName: '', summary: '' })
  // Avoids redundant re-renders when a page republishes an identical summary
  // (e.g. a polling effect firing with unchanged data).
  const lastRef = useRef('')

  const publish = (pageName: string, summary: string) => {
    const key = pageName + '|' + summary
    if (key === lastRef.current) return
    lastRef.current = key
    setValue({ pageName, summary })
  }

  return <Ctx.Provider value={{ ...value, publish }}>{children}</Ctx.Provider>
}

export function usePageContext() {
  return useContext(Ctx)
}
