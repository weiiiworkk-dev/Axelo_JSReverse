import { AppProvider, useApp } from '../context/AppContext'
import { WindowChrome } from '../components/layout/WindowChrome'
import { NavCard } from '../components/layout/NavCard'
import { MainCard } from '../components/layout/MainCard'
import { HomeWorkspace } from '../components/home/HomeWorkspace'
import { ConversationWorkspace } from '../components/conversation/ConversationWorkspace'
import { ComposerBar } from '../components/composer/ComposerBar'

function Shell() {
  const { state } = useApp()
  return (
    <div className="h-screen flex flex-col overflow-hidden bg-[#f0f0f0]">
      <WindowChrome />
      <div className="flex flex-1 p-2.5 gap-2 overflow-hidden min-h-0">
        <NavCard />
        <MainCard>
          {state.activeSessionId ? <ConversationWorkspace /> : <HomeWorkspace />}
          <ComposerBar />
        </MainCard>
      </div>
    </div>
  )
}

export function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  )
}
