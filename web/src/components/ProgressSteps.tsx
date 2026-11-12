import styles from './ProgressSteps.module.css';

const STEPS = ['Applied', 'Reply', 'Interview', 'Offer'] as const;

/** Four thin segments; the reached ones are ink. */
export function ProgressSteps({ step }: { step: number }) {
  const reached = Math.min(Math.max(step, 1), STEPS.length);
  return (
    <span
      className={styles.steps}
      role="img"
      aria-label={`Reached ${STEPS[reached - 1]}, step ${reached} of ${STEPS.length}`}
    >
      {STEPS.map((name, index) => (
        <span key={name} className={styles.segment} data-reached={index < reached || undefined} />
      ))}
    </span>
  );
}
