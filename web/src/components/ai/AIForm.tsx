import { useId, useState, type FormEvent } from 'react';
import { useAIProviders, useLoadModels, useSaveAI } from '../../api/queries';
import type { AIModel, AIStatus } from '../../api/types';
import styles from './AIForm.module.css';

interface Props {
  status: AIStatus | undefined;
  submitLabel?: string;
  onSaved?: () => void;
  extraActions?: React.ReactNode;
}

type Privacy = 'subject_sender' | 'with_body';

export function AIForm({ status, submitLabel = 'Save', onSaved, extraActions }: Props) {
  const providers = useAIProviders();
  const loadModels = useLoadModels();
  const save = useSaveAI();
  const radioName = useId();

  const [provider, setProvider] = useState(status?.provider ?? 'anthropic');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState(status?.base_url ?? '');
  const [models, setModels] = useState<AIModel[] | null>(null);
  const [model, setModel] = useState(status?.model ?? '');
  const [privacy, setPrivacy] = useState<Privacy>((status?.privacy_mode as Privacy) ?? 'subject_sender');
  const [useBatch, setUseBatch] = useState(status?.use_batch ?? true);

  const info = providers.data?.find((p) => p.id === provider);
  const keySaved = Boolean(status?.configured && status.provider === provider && status.has_api_key);
  const showBaseUrl = provider === 'ollama' || Boolean(baseUrl);

  const changeProvider = (next: string) => {
    setProvider(next);
    setModels(null);
    setModel(next === status?.provider ? (status?.model ?? '') : '');
    setBaseUrl(next === status?.provider ? (status?.base_url ?? '') : '');
    loadModels.reset();
  };

  const load = () => {
    loadModels.mutate(
      { provider, api_key: apiKey.trim() || undefined, base_url: baseUrl.trim() || undefined },
      {
        onSuccess: ({ models: listed }) => {
          setModels(listed);
          if (!listed.some((m) => m.id === model)) setModel(listed[0]?.id ?? '');
        },
      },
    );
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate(
      {
        provider,
        model,
        api_key: apiKey.trim() || undefined,
        base_url: baseUrl.trim() || undefined,
        privacy_mode: privacy,
        use_batch: info?.supports_batch ? useBatch : false,
        body_chars: status?.body_chars ?? undefined,
        batch_threshold: status?.batch_threshold ?? undefined,
      },
      { onSuccess: () => onSaved?.() },
    );
  };

  const modelOptions = models ?? (model ? [{ id: model, name: model }] : []);

  return (
    <form className={styles.form} onSubmit={submit}>
      <div className="field">
        <label htmlFor="ai-provider">Provider</label>
        <select
          id="ai-provider"
          className={`input ${styles.select}`}
          value={provider}
          onChange={(event) => changeProvider(event.target.value)}
        >
          {(providers.data ?? [{ id: provider, name: provider }]).map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>
      {info?.needs_api_key !== false && (
        <div className="field">
          <label htmlFor="ai-key">API key</label>
          <input
            id="ai-key"
            className="input mono"
            type="password"
            autoComplete="off"
            value={apiKey}
            placeholder={keySaved ? 'Saved. Leave empty to keep it.' : ''}
            onChange={(event) => setApiKey(event.target.value)}
          />
        </div>
      )}
      {showBaseUrl && (
        <div className="field">
          <label htmlFor="ai-base-url">Base URL</label>
          <input
            id="ai-base-url"
            className="input mono"
            autoComplete="off"
            value={baseUrl}
            placeholder={info?.default_base_url}
            onChange={(event) => setBaseUrl(event.target.value)}
          />
        </div>
      )}
      <div className="field">
        <label htmlFor="ai-model">Model</label>
        <div className={styles.row}>
          <select
            id="ai-model"
            className={`input ${styles.select}`}
            value={model}
            onChange={(event) => setModel(event.target.value)}
            disabled={modelOptions.length === 0}
          >
            {modelOptions.length === 0 && <option value="">Load the models first</option>}
            {modelOptions.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name && m.name !== m.id ? `${m.name} (${m.id})` : m.id}
              </option>
            ))}
          </select>
          <button type="button" className="btn" onClick={load} disabled={loadModels.isPending}>
            {loadModels.isPending ? 'Loading…' : 'Load models'}
          </button>
        </div>
        {loadModels.isError && (
          <p className="error-text" role="alert">
            Couldn’t load models. {loadModels.error.message}
          </p>
        )}
      </div>
      <fieldset className={styles.choices}>
        <legend className="field-label">What the AI sees</legend>
        <label className={styles.choice}>
          <input
            type="radio"
            name={radioName}
            checked={privacy === 'subject_sender'}
            onChange={() => setPrivacy('subject_sender')}
          />
          <span>
            Subject and sender only <span className={styles.hint}>More private, a little less accurate.</span>
          </span>
        </label>
        <label className={styles.choice}>
          <input type="radio" name={radioName} checked={privacy === 'with_body'} onChange={() => setPrivacy('with_body')} />
          <span>
            Subject, sender and the start of the email{' '}
            <span className={styles.hint}>More accurate. The text goes to your provider.</span>
          </span>
        </label>
      </fieldset>
      {info?.supports_batch && (
        <label className={styles.choice}>
          <input type="checkbox" checked={useBatch} onChange={(event) => setUseBatch(event.target.checked)} />
          <span>
            Use batches for large syncs <span className={styles.hint}>About half the price; results can take hours.</span>
          </span>
        </label>
      )}
      {save.isError && (
        <p className="error-text" role="alert">
          {save.error.message}
        </p>
      )}
      <div className={styles.actions}>
        <button type="submit" className="btn btn-primary" disabled={save.isPending || !model}>
          {save.isPending ? 'Saving…' : submitLabel}
        </button>
        {extraActions}
      </div>
    </form>
  );
}
