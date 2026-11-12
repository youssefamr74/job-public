import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAiReview, useAIStatus } from '../../api/queries';
import { aiReviewSummary } from '../../lib/review';
import styles from './AiReviewButton.module.css';

export function AiReviewButton() {
  const ai = useAIStatus();
  const review = useAiReview();
  const [explain, setExplain] = useState(false);
  const notConfigured = ai.data?.configured === false;

  const onClick = () => {
    if (notConfigured) setExplain((value) => !value);
    else review.mutate();
  };

  return (
    <div className={styles.wrap}>
      <button
        type="button"
        className="btn"
        onClick={onClick}
        disabled={ai.isPending || review.isPending}
        aria-expanded={notConfigured ? explain : undefined}
        aria-controls={notConfigured ? 'ai-review-note' : undefined}
      >
        {review.isPending ? 'Reviewing with AI…' : 'Review all with AI'}
      </button>
      {notConfigured && explain && (
        <p id="ai-review-note" className={styles.note}>
          AI isn’t set up. Add a provider and key in <Link to="/settings#ai">Settings › AI</Link>, then come back.
        </p>
      )}
      {review.isSuccess && (
        <p className={styles.note} role="status">
          {aiReviewSummary(review.data)}
        </p>
      )}
      {review.isError && (
        <p className="error-text" role="alert">
          AI review didn’t run. {review.error.message}
        </p>
      )}
    </div>
  );
}
