import { setupWorker } from 'msw/browser';
import { handlers } from './handlers';

/** Starts the in-browser API before the app renders. */
export async function startDemo() {
  // GitHub Pages sends unknown paths to 404.html, which comes back here with the path in ?p=.
  const params = new URLSearchParams(location.search);
  const path = params.get('p');
  if (path?.startsWith(import.meta.env.BASE_URL)) history.replaceState(null, '', path);

  await setupWorker(...handlers).start({
    serviceWorker: { url: `${import.meta.env.BASE_URL}mockServiceWorker.js` },
    onUnhandledRequest: 'bypass',
    quiet: true,
  });
}
