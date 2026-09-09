import { useEffect, useState } from 'react'
import { getDistrictFunding } from '../services/api'
import { Card, DataSourceBadge, Spinner } from '../components/UI'

export default function PestOutbreakReport() {
  const [rows, setRows] = useState<any[] | null>(null)
  useEffect(() => { getDistrictFunding().then(setRows) }, [])
  if (!rows) return <Spinner />
  return <main className="mx-auto max-w-5xl space-y-6 p-6">
    <div className="flex items-center justify-between"><h1 className="text-2xl font-bold">District Agriculture Report</h1><DataSourceBadge status="DEMO" /></div>
    <Card><p className="mb-4 text-sm text-gray-600">Funding coverage context for district-level agricultural planning.</p><div className="space-y-2">{rows.length === 0 && <p className="text-gray-500">No district funding records are available yet.</p>}{rows.map((row) => <div className="flex justify-between border-b py-2" key={row.id}><span>{row.district}</span><span>{row.allocated_cr} Cr allocated</span></div>)}</div></Card>
  </main>
}
