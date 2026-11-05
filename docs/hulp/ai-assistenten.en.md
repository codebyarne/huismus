# AI assistants

You can let an AI assistant, such as ChatGPT, Claude or Gemini, work with
your records. The assistant can then read what's in them, make drafts and,
if you approve, issue and mail. You work in the assistant's app. In Huismus
you only connect it.

## What an assistant can do

- **Read:** the overview (revenue this year, your KOR limit, what's open
  and what's overdue), find and open invoices, credit notes and quotes,
  find customers, and expenses per year. It can't read settings, PDFs,
  mail texts or the mail log.
- **Make drafts:** make and change a draft invoice or quote, and a draft
  credit note for an issued invoice. If the customer isn't in Huismus yet,
  you add them yourself first.
- **Add expenses:** an expense with one or more lines, with the amount you
  paid and an existing category. You change or delete it yourself in
  Huismus.
- **Process receipts:** your assistant reads the receipts without an
  expense and makes an expense from each one, with the receipt attached. It
  doesn't see other attachments.
- **With your permission:** issue an invoice or credit note, send a quote
  (it then gets its number) and mail a document to the customer's e-mail
  address, with the standard text. The assistant first gets a summary to
  show you: the customer, the amount and the number the document will get.
  Then the assistant's app asks for your permission, with a button only you
  can press. If you choose "always allow" there, the app stops asking.
  Huismus can't see that.
- **Never:** change customers or payments, change an expense, mark a quote
  accepted or declined, delete anything, or "Edit anyway".

What the assistant reads goes to the company behind that assistant (OpenAI,
Google or Anthropic). Huismus itself doesn't become reachable from the
internet for this, unless you set up a tunnel yourself.

## The Claude app

If you use the Huismus app on a Mac or Windows computer, you connect the
Claude app with one button:

1. In Huismus, open **Settings → AI assistants** and choose **Connect to
   Claude**.
2. The Claude app opens and asks whether you want to install Huismus.
   Confirm it.
3. Ask Claude something about your records, for example: "Which invoices
   are still unpaid?"

If the Claude app isn't on your computer yet, Huismus says so. Download it
from [claude.ai/download](https://claude.ai/download), then choose
**Connect to Claude** again.

Claude can only reach Huismus while the Huismus window is open. If it's
closed, Claude says Huismus isn't open. If you choose **New key** or
**Disconnect**, the Claude app can't reach it anymore either. To connect
again, choose **Connect to Claude**.

If Huismus runs on a Raspberry Pi or in Docker, this button isn't there.
Use Claude Code instead, below.

## Connecting

1. In Huismus, open **Settings → AI assistants** and choose **Connect**
   under Address and key. Huismus makes a secret key and shows the address
   and the key. The key shows as dots. **Show** reveals it; **Copy** copies
   it without showing it.
2. Give the assistant the address and the key. How you do that is below,
   per assistant. The key goes along as `Authorization: Bearer <key>`.
3. As soon as the assistant has asked something, the page says
   **Connected**.

All assistants that use the address share one key. If you choose **New
key** or **Disconnect**, the old key stops working for everyone. The key
isn't part of a backup. If you restore a backup on another computer, you
connect again.

## Which address to use

The AI assistants page shows the address you have Huismus open at, with
`/mcp` after it. In the desktop app that's `http://127.0.0.1:8765/mcp`. If
port 8765 was taken when the app started, it uses another port, and the
page shows that one. An assistant can only reach the desktop app while its
window is open.

If Huismus runs in Docker, a program on the same computer uses
`http://127.0.0.1:<port>/mcp`, with the port you opened with
`docker run -p`. Add `127.0.0.1` to `ALLOWED_HOSTS` too, for example
`-e ALLOWED_HOSTS=huismus.local,127.0.0.1`. Otherwise Huismus refuses the
request.

## ChatGPT

ChatGPT can't reach an address on your own computer or Pi by itself. It can
through OpenAI's tunnel (Secure MCP Tunnel): a program from OpenAI that you
run next to Huismus. Huismus doesn't include it. You get it, with its
instructions, from OpenAI. Give the tunnel program the address and the key.
Whether and when ChatGPT asks for permission is up to OpenAI.

## Claude Code

```
claude mcp add --transport http huismus http://127.0.0.1:8765/mcp \
  --header "Authorization: Bearer <key>"
```

Claude Code asks for permission before it uses an action of Huismus, unless
you've allowed that action before.

## Gemini CLI

Put this in `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "huismus": {
      "httpUrl": "http://127.0.0.1:8765/mcp",
      "headers": { "Authorization": "Bearer <key>" }
    }
  }
}
```

The Gemini app can't work with custom connections in the Netherlands yet.
