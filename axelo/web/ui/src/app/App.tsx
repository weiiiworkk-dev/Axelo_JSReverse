import { WindowChrome } from '../components/layout/WindowChrome'
import { NavCard } from '../components/layout/NavCard'
import { MainCard } from '../components/layout/MainCard'
import { HomeWorkspace } from '../components/home/HomeWorkspace'
import { ComposerBar } from '../components/composer/ComposerBar'

export function App() {
  return (
    <div className="h-screen flex flex-col overflow-hidden bg-[#f0f0f0]">
      <WindowChrome />
      <div className="flex flex-1 p-2.5 gap-2 overflow-hidden min-h-0">
        <NavCard />
        <MainCard>
          <HomeWorkspace />
          <ComposerBar />
        </MainCard>
      </div>
    </div>
  )
}
