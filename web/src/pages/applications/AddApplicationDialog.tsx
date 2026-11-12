import { useState, type FormEvent } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { useCreateApplication } from '../../api/queries';
import type { BoardStatus } from '../../api/types';
import { StatusSelect } from '../../components/StatusSelect';
import { todayIso } from '../../lib/format';
import dialog from '../../components/Dialog.module.css';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (id: string) => void;
}

export function AddApplicationDialog({ open, onOpenChange, onCreated }: Props) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className={dialog.overlay} />
        <Dialog.Content className={dialog.content}>
          <Dialog.Title className={dialog.title}>Add application</Dialog.Title>
          <Dialog.Description className={dialog.description}>
            For applications Jōb didn’t find in your mail. Later emails about it still attach to it.
          </Dialog.Description>
          {open && (
            <AddApplicationForm
              onCancel={() => onOpenChange(false)}
              onCreated={(id) => {
                onOpenChange(false);
                onCreated(id);
              }}
            />
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function AddApplicationForm({ onCancel, onCreated }: { onCancel: () => void; onCreated: (id: string) => void }) {
  const create = useCreateApplication();
  const [company, setCompany] = useState('');
  const [role, setRole] = useState('');
  const [status, setStatus] = useState<BoardStatus>('Applied');
  const [appliedDate, setAppliedDate] = useState(todayIso());

  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate(
      { company: company.trim(), role: role.trim(), status, applied_date: appliedDate || null },
      { onSuccess: (created) => onCreated(created.id) },
    );
  };

  return (
    <form className={dialog.form} onSubmit={submit}>
      <div className="field">
        <label htmlFor="add-company">Company</label>
        <input
          id="add-company"
          className="input"
          value={company}
          onChange={(event) => setCompany(event.target.value)}
          required
          maxLength={255}
          autoComplete="off"
        />
      </div>
      <div className="field">
        <label htmlFor="add-role">Role</label>
        <input
          id="add-role"
          className="input"
          value={role}
          onChange={(event) => setRole(event.target.value)}
          required
          maxLength={255}
          autoComplete="off"
        />
      </div>
      <div className={dialog.row}>
        <div className="field">
          <label htmlFor="add-status">Status</label>
          <StatusSelect id="add-status" value={status} onChange={setStatus} />
        </div>
        <div className="field">
          <label htmlFor="add-date">Applied</label>
          <input
            id="add-date"
            type="date"
            className="input mono"
            value={appliedDate}
            max={todayIso()}
            onChange={(event) => setAppliedDate(event.target.value)}
          />
        </div>
      </div>
      {create.isError && (
        <p className="error-text" role="alert">
          {create.error.message}
        </p>
      )}
      <div className={dialog.actions}>
        <button type="button" className="btn" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="btn btn-primary" disabled={create.isPending || !company.trim() || !role.trim()}>
          {create.isPending ? 'Adding…' : 'Add application'}
        </button>
      </div>
    </form>
  );
}
