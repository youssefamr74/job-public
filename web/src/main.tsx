import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './styles/global.css';
import { App } from './App';

const root = document.getElementById('root');
if (!root) throw new Error('Missing #root element');

function render(element: HTMLElement) {
  createRoot(element).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

if (__DEMO__) {
  // Only in the demo build; the normal build drops this branch and never bundles src/demo/.
  void import('./demo/start').then(({ startDemo }) => startDemo()).then(() => render(root));
} else {
  render(root);
}
