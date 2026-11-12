import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import styles from './Placeholder.module.css';

interface Props {
  title: string;
  children: ReactNode;
}

export function Placeholder({ title, children }: Props) {
  return (
    <section className={styles.page} aria-labelledby="page-title">
      <h1 id="page-title">{title}</h1>
      <div className={styles.body}>{children}</div>
    </section>
  );
}

export function NotFoundPage() {
  return (
    <Placeholder title="Page not found">
      <p>
        There is nothing at this address. <Link to="/applications">Go to applications</Link>
      </p>
    </Placeholder>
  );
}
