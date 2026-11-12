import { useId, useState, type FormEvent } from 'react';
import { useCountAs, useRoleGroups } from '../../api/queries';
import type { Application, RoleGroups } from '../../api/types';
import styles from './DetailPanel.module.css';

function currentGroup(application: Application, data: RoleGroups | undefined): string {
  if (application.role_group_override) return application.role_group_override;
  let key = application.role_group ?? null;
  const merges = new Map((data?.merges ?? []).map((rule) => [rule.source, rule.target]));
  const seen = new Set<string>();
  while (key !== null && merges.has(key) && !seen.has(key)) {
    seen.add(key);
    key = merges.get(key) ?? key;
  }
  if (key === null) return 'Role not found';
  return data?.groups.find((group) => group.key === key)?.label ?? key.charAt(0).toUpperCase() + key.slice(1);
}

/** Which role group the application counts in on the Analytics page. Kept through syncs. */
export function CountAs({ application }: { application: Application }) {
  const groups = useRoleGroups();
  const countAs = useCountAs();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState('');
  const inputId = useId();
  const listId = useId();

  const save = (group: string) =>
    countAs.mutate({ id: application.id, group }, { onSuccess: () => setEditing(false) });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save(value.trim());
  };

  return (
    <div className={styles.wide}>
      <dt>Counts as in Analytics</dt>
      <dd>
        {editing ? (
          <form className={styles.countAs} onSubmit={submit}>
            <label htmlFor={inputId} className="visually-hidden">
              Count as
            </label>
            <input
              id={inputId}
              className="input"
              list={listId}
              value={value}
              maxLength={255}
              placeholder="A role group"
              autoFocus
              onChange={(event) => setValue(event.target.value)}
            />
            <datalist id={listId}>
              {(groups.data?.groups ?? []).map((group) => (
                <option key={group.key} value={group.label} />
              ))}
            </datalist>
            <button type="submit" className="btn btn-primary" disabled={countAs.isPending || !value.trim()}>
              Save
            </button>
            <button type="button" className="btn" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </form>
        ) : (
          <span className={styles.countAsValue}>
            <span>{currentGroup(application, groups.data)}</span>
            {application.role_group_override && <span className="muted">(set by you)</span>}
            <button
              type="button"
              className="link-button"
              onClick={() => {
                setValue(application.role_group_override ?? '');
                setEditing(true);
              }}
            >
              Change
            </button>
            {application.role_group_override && (
              <button type="button" className="link-button" disabled={countAs.isPending} onClick={() => save('')}>
                Use the role’s group
              </button>
            )}
          </span>
        )}
        {countAs.isError && (
          <p className="error-text" role="alert">
            Not saved: {countAs.error.message}
          </p>
        )}
      </dd>
    </div>
  );
}
