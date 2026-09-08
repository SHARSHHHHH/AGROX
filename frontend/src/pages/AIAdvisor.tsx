import { AdvisorChatPanel } from '../components/AdvisorChatPanel'

export default function AIAdvisor() {
  return (
    <div className="max-w-3xl mx-auto flex flex-col h-[calc(100vh-8rem)]">
      <AdvisorChatPanel variant="full" />
    </div>
  )
}
