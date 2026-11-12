# Setting up AI (optional)

Jōb works without AI. The rule-based classifier handles most emails, and anything it can't settle
goes to **Needs Review**. With AI turned on, Jōb sends only those unsettled emails to the AI provider
you choose. It also uses AI for the companion chat, check-in moments, the weekly review text, mood
insights and the CV summary.

**You need an API key or a local model.** App subscriptions such as Claude Pro, ChatGPT Plus or
Gemini Advanced can't be used: they don't come with API access. API usage is billed separately by
each provider, or it's free if you run a local model with Ollama.

Your API key is stored encrypted in Jōb's `data` folder, on your own computer. It's never logged and
never shown again after you save it.

## What gets sent

Only emails the rules couldn't settle go to AI: those with an unclear status (they would land in
Needs Review) or an unknown company or role. Everything else stays on your computer.

You choose how much of each of those emails is sent:

| Privacy mode | What the provider receives |
| --- | --- |
| **Subject and sender** (default) | The sender and the subject line. |
| **With body** | The sender, the subject, and the first part of the cleaned body text (500 characters by default, adjustable from 100 to 3000). Links, images and formatting are removed. |

Jōb also sends its own guess (company, role, status) so the AI only has to fill the gaps. The AI
answers in a fixed format, which Jōb checks. If the answer is invalid twice, or the provider is down,
Jōb keeps the rule-based result. The text of an email is always treated as data: instructions
inside an email can't change what Jōb asks or what it accepts back.

For the other features, the provider receives your application statistics (counts, statuses and
company names), your chat messages, and your CV if you upload one.

## Choosing a provider

In Jōb's settings, pick a provider, paste your key, and choose a model. The model list is loaded
live from the provider, so you always see what your key can use. A small, cheap model is plenty for
classification. Use **Test** to check the connection before your first sync.

Before a large first run, use **Estimate**. It runs the rules over your mail without saving anything
and tells you how many emails would go to AI, roughly how many tokens that is, and the approximate
cost if Jōb knows the model's price (see `backend/ai/prices.json`, which you can edit).

### Ollama (local, free)

Ollama runs models on your own computer. Nothing leaves your machine.

1. Install Ollama from <https://ollama.com/download> and start it.
2. Pull a model, for example: `ollama pull llama3.2`. Small models (3–8B) are fast enough for
   classification on most laptops.
3. In Jōb, choose **Ollama**. No key is needed. The base URL defaults to
   `http://localhost:11434/v1`; change it if Ollama runs elsewhere.

Local models vary in how well they follow the answer format. If one keeps failing, try a different
model; Jōb falls back to the rules result in the meantime.

### Anthropic (Claude)

1. Create an API key in the Anthropic Console: <https://console.anthropic.com/settings/keys>.
   Add credit under Billing.
2. In Jōb, choose **Anthropic** and paste the key.

Supports batches (see below), and the CV is sent as a PDF directly.

### OpenAI

1. Create an API key at <https://platform.openai.com/api-keys> and add credit to your account.
2. In Jōb, choose **OpenAI** and paste the key.

Supports batches. For the CV, Jōb extracts the text locally and sends the text.

### Google Gemini

1. Create an API key in Google AI Studio: <https://aistudio.google.com/apikey>.
2. In Jōb, choose **Google Gemini** and paste the key.

Jōb uses Gemini's OpenAI-compatible endpoint. Google's terms treat free-tier and paid usage
differently; check them before sending email text.

### OpenRouter

OpenRouter gives one key for many models from different companies.

1. Create a key at <https://openrouter.ai/keys> and add credit.
2. In Jōb, choose **OpenRouter** and paste the key.

## Batches

Anthropic and OpenAI offer batch processing at about half the price. Results can take minutes to
hours (up to 24 hours). Jōb uses a batch when:

- the provider supports it,
- **Use batch** is on, and
- the number of emails to send is at least the batch threshold (50 by default).

Otherwise it sends emails one by one, a few at a time. While a batch is pending, those emails are
held back: the mail cursor doesn't move past them, so nothing is lost if Jōb is closed. Jōb checks
pending batches every minute and when it starts, then saves the results with the next sync.

## Reviewing what's already saved

**Let AI review Needs Review** sends your Needs Review applications, and those with an unknown
company or role, to AI. Jōb fetches the original emails again from your mailbox to do this.
Applications you edited by hand are never changed.

## Turning AI off

Remove the AI settings in Jōb (or call `DELETE /ai`). The key is deleted, and Jōb goes back to
rules only.
