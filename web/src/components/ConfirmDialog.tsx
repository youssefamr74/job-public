import { useState, type ReactNode } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import styles from './Dialog.module.css';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  pending?: boolean;
  error?: string | null;
  /** A word the user has to type before the action is allowed, e.g. DELETE. */
  typeToConfirm?: string;
}

export function ConfirmDialog(props: Props) {
  return (
    <Dialog.Root open={props.open} onOpenChange={props.onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className={styles.overlay} />
        <Dialog.Content className={styles.content}>
          {props.open && <Body {...props} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Body({ title, children, confirmLabel, onConfirm, pending, error, typeToConfirm, onOpenChange }: Props) {
  const [typed, setTyped] = useState('');
  const allowed = !typeToConfirm || typed === typeToConfirm;

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (allowed && !pending) onConfirm();
      }}
    >
      <Dialog.Title className={styles.title}>{title}</Dialog.Title>
      <Dialog.Description asChild>
        <div className={styles.description}>{children}</div>
      </Dialog.Description>
      <div className={styles.form}>
        {typeToConfirm && (
          <div className="field">
            <label htmlFor="confirm-word">
              Type <span className="mono">{typeToConfirm}</span> to confirm
            </label>
            <input
              id="confirm-word"
              className="input mono"
              autoComplete="off"
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
            />
          </div>
        )}
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}
        <div className={styles.actions}>
          <button type="button" className="btn" onClick={() => onOpenChange(false)}>
            Cancel
          </button>
          <button type="submit" className={`btn ${styles.danger}`} disabled={!allowed || pending}>
            {pending ? 'Working…' : confirmLabel}
          </button>
        </div>
      </div>
    </form>
  );
}
