import { useState, type FormEvent } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { useUpdateDetails } from '../../api/queries';
import type { Application } from '../../api/types';
import { isMissing } from '../../lib/applications';
import dialog from '../../components/Dialog.module.css';

interface Props {
  application: Application;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EditDetailsDialog({ application, open, onOpenChange }: Props) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className={dialog.overlay} />
        <Dialog.Content className={dialog.content}>
          <Dialog.Title className={dialog.title}>Edit details</Dialog.Title>
          <Dialog.Description className={dialog.description}>
            Your edits always win over the next sync.
          </Dialog.Description>
          {open && <EditForm application={application} onDone={() => onOpenChange(false)} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function EditForm({ application, onDone }: { application: Application; onDone: () => void }) {
  const update = useUpdateDetails();
  const [company, setCompany] = useState(isMissing(application.company) ? '' : (application.company ?? ''));
  const [role, setRole] = useState(isMissing(application.role) ? '' : (application.role ?? ''));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const changes: { company?: string; role?: string } = {};
    if (company.trim() !== (application.company ?? '')) changes.company = company.trim();
    if (role.trim() !== (application.role ?? '')) changes.role = role.trim();
    if (Object.keys(changes).length === 0) {
      onDone();
      return;
    }
    update.mutate({ id: application.id, changes }, { onSuccess: onDone });
  };

  return (
    <form className={dialog.form} onSubmit={submit}>
      <div className="field">
        <label htmlFor="edit-company">Company</label>
        <input
          id="edit-company"
          className="input"
          value={company}
          onChange={(event) => setCompany(event.target.value)}
          required
          maxLength={255}
          autoComplete="off"
        />
      </div>
      <div className="field">
        <label htmlFor="edit-role">Role</label>
        <input
          id="edit-role"
          className="input"
          value={role}
          onChange={(event) => setRole(event.target.value)}
          required
          maxLength={255}
          autoComplete="off"
        />
      </div>
      {update.isError && (
        <p className="error-text" role="alert">
          {update.error.message}
        </p>
      )}
      <div className={dialog.actions}>
        <button type="button" className="btn" onClick={onDone}>
          Cancel
        </button>
        <button type="submit" className="btn btn-primary" disabled={update.isPending || !company.trim() || !role.trim()}>
          {update.isPending ? 'Saving…' : 'Save'}
        </button>
      </div>
    </form>
  );
}
