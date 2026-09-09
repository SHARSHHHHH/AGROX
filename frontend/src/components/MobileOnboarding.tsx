import { useState } from 'react'

const STORAGE_KEY = 'agrox-mobile-onboarding-seen'
export const hasSeenOnboarding = () => localStorage.getItem(STORAGE_KEY) === '1'

export function MobileOnboarding({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(0)
  const slides = [
    ['Set up your farm', 'Add your crop, location, soil, and irrigation details.'],
    ['Get grounded advice', 'Use alerts, crop guidance, pest analysis, and weather together.'],
    ['Stay connected', 'Track harvests, land contracts, and marketplace activity in one place.'],
  ]
  const finish = () => { localStorage.setItem(STORAGE_KEY, '1'); onDone() }
  return <div className="fixed inset-0 z-50 flex items-end bg-black/40 p-4 sm:items-center sm:justify-center">
    <section className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl"><p className="text-sm text-gray-500">{step + 1} / {slides.length}</p><h2 className="mt-3 text-2xl font-bold">{slides[step][0]}</h2><p className="mt-2 text-gray-600">{slides[step][1]}</p><div className="mt-6 flex justify-end gap-2">{step > 0 && <button className="px-4 py-2 text-gray-600" onClick={() => setStep(step - 1)}>Back</button>}{step < slides.length - 1 ? <button className="rounded-lg bg-field-600 px-4 py-2 text-white" onClick={() => setStep(step + 1)}>Next</button> : <button className="rounded-lg bg-field-600 px-4 py-2 text-white" onClick={finish}>Start</button>}</div></section>
  </div>
}
