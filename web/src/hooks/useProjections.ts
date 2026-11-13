import { useCallback, useEffect, useState } from 'react';
import { DATA_URL } from '../config';
import { parseProjections, type Projections } from '../types';

export type ProjectionsState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: Projections };

export function useProjections(): { state: ProjectionsState; retry: () => void } {
  const [state, setState] = useState<ProjectionsState>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: 'loading' });

    fetch(DATA_URL, { signal: controller.signal, cache: 'no-cache' })
      .then((res) => {
        if (!res.ok) throw new Error(`Could not load projections (HTTP ${res.status}).`);
        return res.json() as Promise<unknown>;
      })
      .then((json) => setState({ status: 'ready', data: parseProjections(json) }))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        const message = err instanceof Error ? err.message : 'Could not load projections.';
        setState({ status: 'error', message });
      });

    return () => controller.abort();
  }, [attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { state, retry };
}
