# Connecting Gmail

Jōb only reads your mail. It never sends, deletes or changes anything. You can connect Gmail in
one of two ways:

- **Option A: app password (recommended).** Takes a few minutes and keeps working until you remove it.
- **Option B: your own Google Cloud app.** For accounts that can't use app passwords, such as
  accounts with Advanced Protection. It takes longer to set up.

Your password or tokens are stored encrypted in Jōb's `data` folder, on your own computer.

## Option A: app password

1. **Turn on 2-Step Verification.** App passwords only work with it. Go to
   <https://myaccount.google.com/security> and turn on 2-Step Verification if it's off.
2. **IMAP is already on.** Since January 2025 Gmail always allows IMAP for personal accounts, so
   there's nothing to switch on. For a work or school account, your admin decides.
3. **Create an app password.** Go to <https://myaccount.google.com/apppasswords>, type a name such
   as `Jōb`, and create it. Google shows a 16-character password **once**. Copy it now.
4. **Paste it into Jōb.** In setup, choose **App password**, then enter:
   - **Gmail address**: your full address, like `name@gmail.com`
   - **App password**: the 16 characters. Spaces don't matter.

   Jōb signs in to check it before saving anything.

If you can't find the app password page, Google doesn't offer app passwords for your account. This
happens with Advanced Protection, with 2-Step Verification that uses only security keys, and with
most work or school accounts. Use Option B instead.

If you change your Google password, Google removes your app passwords. Create a new one and enter
it again in Jōb.

## Option B: your own Google Cloud app

You create a small private app in Google Cloud that only you use, and give it read-only access to
your Gmail.

1. **Create a project.** Go to <https://console.cloud.google.com/> and create a new project. Any name works.
2. **Enable the Gmail API.** Open **Menu > APIs & Services > Library**, search for **Gmail API**,
   open it and click **Enable**.
3. **Set up the consent screen.** Open **Menu > Google Auth platform > Branding**. If it says
   "Google Auth platform not configured yet", click **Get Started** and fill in:
   - **App name**: for example `Jōb`
   - **User support email**: your address
   - **Audience**: **External**
   - **Contact information**: your address

   Then agree to the policy and click **Create**.
4. **Add yourself as a test user.** Open **Audience**, under **Test users** click **Add users**,
   enter your Gmail address and click **Save**.
5. **Add the Gmail scope.** Open **Data Access**, click **Add or Remove Scopes**, find
   `https://www.googleapis.com/auth/gmail.readonly` (Gmail API, read-only), select it and click **Save**.
6. **Create the client.** Open **Clients** and click **Create Client**.
   - **Application type**: **Web application**
   - **Name**: anything, for example `Jōb local`
   - Under **Authorized redirect URIs**, click **Add URI** and paste the **redirect URI** that Jōb
     shows in setup (with a copy button). It looks like `http://127.0.0.1:8000/mail/oauth/callback`
     and must match exactly, including `http`, the port and no trailing slash.

   Click **Create**.
7. **Copy the client ID and secret.** Google shows the **client secret only once**, right after you
   create the client, so copy both now. The client ID ends in `.apps.googleusercontent.com`.
8. **Paste them into Jōb.** In setup, choose **Google Cloud app**, enter the **Client ID** and
   **Client secret**, and continue. Google asks you to sign in and allow read-only Gmail access.
   Google will warn that the app isn't verified; that's expected for your own private app, so
   continue. When it's done, you're sent back to Jōb's setup page.

### The 7-day limit in Testing mode

While your Google Cloud app is in **Testing** (the default for a new External app), Google gives
it access for only **7 days**. After that, Jōb shows **Reconnect Gmail**. Reconnect from setup;
Jōb remembers your client ID and secret, so you only sign in again.

## Disconnecting

**Disconnect** in Jōb deletes the stored password or tokens. For Option B it also asks Google to
revoke Jōb's access. You can also remove access yourself at any time: delete the app password at
<https://myaccount.google.com/apppasswords>, or remove the app at
<https://myaccount.google.com/connections>.
