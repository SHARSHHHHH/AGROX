import { useEffect, useState } from 'react'
import { getFundingOverview, getSchemeBudgetList } from '../services/api'
import { Card, DataSourceBadge, Spinner } from '../components/UI'

export default function GovernmentBrief() {
  const [overview, setOverview] = useState<any>(null)
  const [schemes, setSchemes] = useState<any[]>([])
  useEffect(() => {
    Promise.all([getFundingOverview(), getSchemeBudgetList()]).then(([summary, rows]) => {
      setOverview(summary)
      setSchemes(rows)
    })
  }, [])
  if (!overview) return <Spinner />
  return <main className="mx-auto max-w-5xl space-y-6 p-6">
    <div className="flex items-center justify-between"><h1 className="text-2xl font-bold">Government Funding Brief</h1><DataSourceBadge status={overview.data_status} /></div>
    <Card><p className="text-sm text-gray-500">Financial year {overview.financial_year}</p><div className="mt-3 grid gap-4 sm:grid-cols-3"><div><b>{overview.scheme_count}</b><p className="text-sm text-gray-500">Schemes</p></div><div><b>{overview.budget_total_cr}</b><p className="text-sm text-gray-500">Budget (crore)</p></div><div><b>{overview.allocated_total_cr}</b><p className="text-sm text-gray-500">Allocated (crore)</p></div></div></Card>
    <Card><h2 className="mb-3 font-semibold">Scheme budgets</h2><div className="space-y-2">{schemes.map((row) => <div className="flex justify-between border-b py-2" key={row.id}><span>{row.scheme_name}</span><span>{row.budget_estimate_cr ?? 'Not available'} Cr</span></div>)}</div></Card>
  </main>
}
