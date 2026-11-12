import * as Select from '@radix-ui/react-select';
import { BOARD_STATUSES, type BoardStatus } from '../api/types';
import { statusClass } from '../lib/applications';
import { CheckIcon, ChevronDownIcon } from './Icons';
import styles from './StatusSelect.module.css';

interface Props {
  id: string;
  value: BoardStatus;
  onChange: (value: BoardStatus) => void;
}

export function StatusSelect({ id, value, onChange }: Props) {
  return (
    <Select.Root value={value} onValueChange={(next) => onChange(next as BoardStatus)}>
      <Select.Trigger id={id} className={`input ${styles.trigger}`}>
        <Select.Value />
        <Select.Icon className={styles.icon}>
          <ChevronDownIcon />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content className="overlay-menu" position="popper" sideOffset={4}>
          <Select.Viewport>
            {BOARD_STATUSES.map((status) => (
              <Select.Item key={status} value={status} className="overlay-item">
                <Select.ItemText>
                  <span className={statusClass(status)}>{status}</span>
                </Select.ItemText>
                <Select.ItemIndicator>
                  <CheckIcon />
                </Select.ItemIndicator>
              </Select.Item>
            ))}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}
