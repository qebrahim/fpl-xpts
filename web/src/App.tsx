import { useState } from 'react';
import { Footer } from './components/Footer';
import { Header } from './components/Header';
import { ErrorState, LoadingState } from './components/States';
import { panelId, tabId, Tabs, type TabDef } from './components/Tabs';
import { TopPlayers } from './components/TopPlayers';
import { useProjections, type ProjectionsState } from './hooks/useProjections';
import { useTheme } from './hooks/useTheme';

type View = 'top' | 'builder';

const TABS: ReadonlyArray<TabDef<View>> = [
  { id: 'top', label: 'Top players' },
  { id: 'builder', label: 'Team builder', disabled: true, tag: 'Soon' },
];

export function App() {
  const { theme, toggle } = useTheme();
  const { state, retry } = useProjections();
  const [view, setView] = useState<View>('top');

  return (
    <div className="page">
      <Header
        data={state.status === 'ready' ? state.data : null}
        loading={state.status === 'loading'}
        theme={theme}
        onToggleTheme={toggle}
      />
      <Tabs tabs={TABS} active={view} onChange={setView} label="Views" />
      <main className="main">
        <div id={panelId(view)} role="tabpanel" aria-labelledby={tabId(view)}>
          {view === 'top' && <TopPlayersView state={state} onRetry={retry} />}
        </div>
      </main>
      <Footer />
    </div>
  );
}

function TopPlayersView({ state, onRetry }: { state: ProjectionsState; onRetry: () => void }) {
  switch (state.status) {
    case 'loading':
      return <LoadingState />;
    case 'error':
      return <ErrorState message={state.message} onRetry={onRetry} />;
    case 'ready':
      return <TopPlayers data={state.data} />;
  }
}
