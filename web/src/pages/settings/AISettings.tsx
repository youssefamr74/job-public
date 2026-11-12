import { useState } from 'react';
import { useAIProviders, useAIStatus, useRemoveAI, useTestAI } from '../../api/queries';
import { AIForm } from '../../components/ai/AIForm';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ErrorState, Loading } from '../../components/States';
import { plural } from '../../lib/format';
import styles from './SettingsPage.module.css';

const PRIVACY: Record<string, string> = {
  subject_sender: 'subject and sender only',
  with_body: 'with the start of each email',
};

export function AISettings() {
  const ai = useAIStatus();
  const providers = useAIProviders();
  const test = useTestAI();
  const remove = useRemoveAI();
  const [confirming, setConfirming] = useState(false);
  const [saved, setSaved] = useState(false);

  if (ai.isPending) return <Loading>Loading AI settings…</Loading>;
  if (ai.isError) {
    return <ErrorState message={`Couldn’t load AI settings. ${ai.error.message}`} onRetry={() => void ai.refetch()} />;
  }
  const status = ai.data;
  const providerName = providers.data?.find((p) => p.id === status.provider)?.name ?? status.provider;

  return (
    <>
      {status.configured ? (
        <p className={styles.plain}>
          <strong>{providerName}</strong> · <span className="mono">{status.model}</span> · {PRIVACY[status.privacy_mode ?? ''] ?? status.privacy_mode}
          {status.pending_batches > 0 && <> · {plural(status.pending_batches, 'batch', 'batches')} waiting</>}
        </p>
      ) : (
        <p className={styles.plain}>
          <strong>Not configured.</strong> Jōb works without AI; the rules sort most emails. AI helps with the ones
          they can’t, and writes the weekly review.
        </p>
      )}
      {saved && (
        <p className={styles.success} role="status">
          Saved.
        </p>
      )}
      <AIForm
        key={`${status.provider ?? 'none'}-${status.model ?? ''}`}
        status={status}
        submitLabel={status.configured ? 'Save changes' : 'Save'}
        onSaved={() => {
          setSaved(true);
          test.reset();
        }}
        extraActions={
          status.configured && (
            <>
              <button type="button" className="btn" onClick={() => test.mutate()} disabled={test.isPending}>
                {test.isPending ? 'Testing…' : 'Test'}
              </button>
              <button type="button" className="btn" onClick={() => setConfirming(true)}>
                Remove
              </button>
            </>
          )
        }
      />
      {test.data && (
        <p className={test.data.ok ? styles.success : 'error-text'} role="status">
          {test.data.ok
            ? test.data.structured_output
              ? 'Works. The model answered in the expected format.'
              : 'The model answered, but not in the expected format. Try another model.'
            : test.data.message}
        </p>
      )}
      {test.isError && (
        <p className="error-text" role="alert">
          {test.error.message}
        </p>
      )}
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Remove AI?"
        confirmLabel="Remove"
        pending={remove.isPending}
        error={remove.error?.message ?? null}
        onConfirm={() =>
          remove.mutate(undefined, {
            onSuccess: () => {
              setConfirming(false);
              setSaved(false);
            },
          })
        }
      >
        <p>The provider, model and key are deleted from this computer. Sorting goes back to the rules only.</p>
      </ConfirmDialog>
    </>
  );
}
