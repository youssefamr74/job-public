import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { BOARD_STATUSES } from '../../api/types';
import { DATE_RANGES, type DateRange, type Filters } from '../../lib/applications';
import { CheckIcon } from '../../components/Icons';
import styles from './FilterBar.module.css';

interface Props {
  filters: Filters;
  onChange: (changes: Partial<Filters>) => void;
  summary: string;
}

export function FilterBar({ filters, onChange, summary }: Props) {
  const rangeLabel = DATE_RANGES.find((range) => range.value === filters.range)?.label ?? 'All time';

  return (
    <div className={styles.bar}>
      <div className={styles.filters} role="group" aria-label="Filters">
        <DropdownMenu.Root>
          <DropdownMenu.Trigger className={`btn ${styles.filter}`}>
            Status: {filters.status ?? 'All'}
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content className="overlay-menu" align="start" sideOffset={4}>
              <DropdownMenu.RadioGroup
                value={filters.status ?? 'all'}
                onValueChange={(value) => onChange({ status: value === 'all' ? null : value })}
              >
                {['all', ...BOARD_STATUSES].map((value) => (
                  <DropdownMenu.RadioItem key={value} value={value} className="overlay-item">
                    {value === 'all' ? 'All statuses' : value}
                    <DropdownMenu.ItemIndicator>
                      <CheckIcon />
                    </DropdownMenu.ItemIndicator>
                  </DropdownMenu.RadioItem>
                ))}
              </DropdownMenu.RadioGroup>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>

        <DropdownMenu.Root>
          <DropdownMenu.Trigger
            className={`btn ${styles.filter}`}
            aria-label={`Applied date: ${rangeLabel}`}
          >
            {rangeLabel}
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content className="overlay-menu" align="start" sideOffset={4}>
              <DropdownMenu.Label className="overlay-label">Applied in</DropdownMenu.Label>
              <DropdownMenu.RadioGroup
                value={filters.range}
                onValueChange={(value) => onChange({ range: value as DateRange })}
              >
                {DATE_RANGES.map((range) => (
                  <DropdownMenu.RadioItem key={range.value} value={range.value} className="overlay-item">
                    {range.label}
                    <DropdownMenu.ItemIndicator>
                      <CheckIcon />
                    </DropdownMenu.ItemIndicator>
                  </DropdownMenu.RadioItem>
                ))}
              </DropdownMenu.RadioGroup>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>

        <button
          type="button"
          className={`btn ${styles.filter}`}
          aria-pressed={filters.noReply}
          onClick={() => onChange({ noReply: !filters.noReply })}
        >
          No reply 14+ days
        </button>
      </div>
      <p className={styles.summary} aria-live="polite">
        {summary}
      </p>
    </div>
  );
}
