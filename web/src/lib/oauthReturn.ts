const KEY = 'job.oauthReturn';

/** Google sends the browser back to /setup; this remembers where the user started (e.g. Settings). */
export function rememberOAuthReturn(path: string) {
  try {
    sessionStorage.setItem(KEY, path);
  } catch {
    /* storage can be unavailable; the user then lands on /setup, which still works */
  }
}

export function takeOAuthReturn(): string | null {
  try {
    const path = sessionStorage.getItem(KEY);
    sessionStorage.removeItem(KEY);
    return path && path.startsWith('/') ? path : null;
  } catch {
    return null;
  }
}

const REASONS: Record<string, string> = {
  access_denied: 'Access wasn’t granted in Google. Try again and allow read access to Gmail.',
  invalid_state: 'The sign-in link expired. Start the connection again.',
  authorization_failed: 'Google didn’t finish the sign-in. Try again.',
  no_refresh_token:
    'Google didn’t return a refresh token. Remove Jōb’s access in your Google Account, then connect again.',
  network: 'Couldn’t reach Google. Check your internet connection and try again.',
};

export function oauthErrorText(reason: string | null): string {
  return (reason && REASONS[reason]) || 'Connecting Gmail didn’t work. Check the client ID and secret, then try again.';
}
