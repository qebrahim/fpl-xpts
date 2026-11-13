import { useRef, type KeyboardEvent } from 'react';

export interface TabDef<Id extends string> {
  id: Id;
  label: string;
  disabled?: boolean;
  tag?: string;
}

interface TabsProps<Id extends string> {
  tabs: ReadonlyArray<TabDef<Id>>;
  active: Id;
  onChange: (id: Id) => void;
  label: string;
}

export const tabId = (id: string) => `tab-${id}`;
export const panelId = (id: string) => `panel-${id}`;

/** WAI-ARIA tabs with roving focus; disabled tabs stay focusable but cannot be selected. */
export function Tabs<Id extends string>({ tabs, active, onChange, label }: TabsProps<Id>) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const current = refs.current.findIndex((el) => el === document.activeElement);
    if (current < 0) return;
    const last = tabs.length - 1;
    const target =
      event.key === 'ArrowRight' ? (current === last ? 0 : current + 1)
      : event.key === 'ArrowLeft' ? (current === 0 ? last : current - 1)
      : event.key === 'Home' ? 0
      : event.key === 'End' ? last
      : null;
    if (target === null) return;
    event.preventDefault();
    refs.current[target]?.focus();
  };

  return (
    <div className="tabs" role="tablist" aria-label={label} onKeyDown={onKeyDown}>
      {tabs.map((tab, i) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="tab"
            id={tabId(tab.id)}
            className="tab"
            aria-selected={selected}
            aria-controls={selected ? panelId(tab.id) : undefined}
            aria-disabled={tab.disabled || undefined}
            tabIndex={selected ? 0 : -1}
            onClick={() => {
              if (!tab.disabled) onChange(tab.id);
            }}
          >
            {tab.label}
            {tab.tag && <span className="tab__tag">{tab.tag}</span>}
          </button>
        );
      })}
    </div>
  );
}
