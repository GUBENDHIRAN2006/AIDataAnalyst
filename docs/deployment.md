# Deploy the frontend, API, and database

This project uses three connected services:

- **Vercel** hosts the Next.js frontend in `frontend/`.
- **Render** hosts the FastAPI service from the repository root.
- **Supabase** provides authentication and user-owned analysis history.

The browser calls same-origin Next.js route handlers. Those server routes call
Render with the internal `APP_API_KEY`; that key is never sent to browser code.
FastAPI uses the Supabase URL and anon/publishable key from Render's environment.

## 1. Push the project to GitHub

Create a GitHub repository and push the project files, including `render.yaml`
and the `frontend/` folder. Do not add `.env`, API keys, or database passwords.

## 2. Prepare Supabase

1. Create a Supabase project.
2. In **SQL Editor**, run `supabase/analysis_history.sql`.
3. In **Authentication → URL Configuration**, set the Site URL to the eventual
   Vercel domain. Add the Vercel preview/production callback URLs if email
   confirmation is enabled.
4. Enable email/password sign-in and choose the email-confirmation and password
   rules for the app.
5. Copy the project URL and the **anon/publishable** API key. Never use the
   `service_role` key.

To import tables from Supabase, the project must also have its Data API enabled.
Make sure the table's schema (commonly `public`) is exposed in the Data API
settings and the key's database role has `SELECT` permission. Row-level security
must allow that role to read rows; for user-specific policies, enter a valid
user access token in the database connection form. Do not grant anonymous access
to sensitive tables just to make discovery work.

## 3. Deploy FastAPI on Render

1. The repository pins Render to Python 3.12 using `.python-version`.
   This avoids the Python 3.14 source build failure for the project's pinned
   Pydantic Core dependency.
2. In Render, choose **New → Blueprint** and select the GitHub repository.
   Render reads `render.yaml` and creates the `ai-data-analyst-api` service.
3. In the service's environment settings, fill in `GROQ_API_KEY`,
   `SUPABASE_URL`, and `SUPABASE_ANON_KEY`.
   The blueprint caps Groq responses at 1,024 output tokens by default to
   reduce tokens-per-minute usage. Increase `GROQ_MAX_TOKENS` only if your
   Groq plan has enough TPM capacity.
4. Deploy and wait for the health check. Open
   `https://<your-render-service>.onrender.com/health`; it should return
   `{"status":"ok"}`.
5. Copy the generated `APP_API_KEY` value from Render's environment settings.
   Treat it as a secret.

## 4. Deploy Next.js on Vercel

1. In Vercel, import the same GitHub repository.
2. Set **Root Directory** to `frontend` and leave framework detection set to
   Next.js.
3. Add these server-side environment variables:

   | Name | Value |
   |---|---|
   | `BACKEND_API_URL` | `https://<your-render-service>.onrender.com` |
   | `APP_API_KEY` | The exact generated `APP_API_KEY` from Render |

   Do **not** prefix either variable with `NEXT_PUBLIC_`. Do not add Supabase
   secrets or the Render API key to client-side code.
4. Deploy, sign in with the administrator account, and open `/integrations` on
   the Vercel URL. Render should report **Connected**; Supabase should report
   **Connected** after its settings are entered on Render. The integrations
   page is restricted to `gubendhiran0710@gmail.com`.

## Connecting MySQL Workbench databases

The MySQL form uses the connection's **TCP/IP server hostname**, port (usually
`3306`), database/schema name, username, and password. A Workbench saved
connection name is only a local label and is not a server address.

When using the deployed app, the FastAPI service on Render—not Workbench or your
browser—opens the database connection. The MySQL server must be reachable from
Render: use a public database endpoint, allow the Render service's outbound IP
addresses in the provider firewall, and grant a least-privilege account
`SELECT` access from that remote host. A MySQL server running on your computer
or addressed as `localhost`/`127.0.0.1` cannot be reached by Render. Do not
expose a local database to the public internet to work around this; use a
properly secured hosted database or run the application backend in a trusted
network that can reach the server.

For a local development deployment, run FastAPI on a machine/network that can
reach the MySQL server and enter the same TCP/IP host and port shown in
Workbench. Keep TLS verification enabled for public servers; only disable TLS
for a trusted local development connection when the server does not support it.

## 5. Verify end-to-end

1. Use the Vercel site to create an account and sign in.
2. If email confirmation is enabled, confirm the message sent by Supabase and
   then sign in.
3. Import a small CSV or connect a read-only database and choose a table.
4. Review the preview and click **Start analysis in chat**. Ask questions and
   follow-ups; text, result tables, and supported charts appear in the chat.
   Signed-in users can view saved history on the chat page.
5. From the administrator account, visit `/integrations` to check Vercel,
   Render, and Supabase status. Other signed-in users can access the workspace
   and chat but do not see the integrations navigation option.

The interface limits datasets to about 2.9 MB for analysis requests. This
leaves room for chat history and keeps the request below Render's 3 MB
backend limit. Use smaller tables; larger production data flows should be
redesigned around paginated queries or private object storage rather than
raising this limit.
The active dataset and chat transcript are stored in browser-local IndexedDB.
They are saved when a CSV or database table is loaded, restored on the workspace
page, and retained when navigating to and from chat or refreshing the page.
Clear the workspace/browser data on shared devices.

## Important security and runtime notes

- Keep `APP_API_KEY`, `GROQ_API_KEY`, and the Supabase anon key in Render/Vercel
  environment settings, not source control. `APP_API_KEY` must match on Render
  and Vercel.
- Supabase user history is protected by the SQL migration's row-level security
  policies. Review RLS before exposing any additional tables.
- Use least-privilege, read-only credentials and TLS when connecting external
  databases. Avoid service-role credentials for user database connections.
- Render free instances may sleep when idle. The first request after idle can
  take longer; use an always-on plan for latency-sensitive production use.
- Groq 429 rate-limit responses mean the model or organization quota was
  exceeded. Tokens-per-minute usage includes the prompt and response and is
  shared with other applications using the same Groq organization. Wait for the
  quota window to reset, reduce dataset/chat context, or use a model/account
  with higher capacity. `GROQ_MAX_TOKENS` only caps response length; it does not
  increase the organization's quota. Explicit chart requests are generated
  locally from the imported data and do not require a Groq request.
- This repository does not include the user's provider credentials and cannot
  create services or deploy on their accounts. The steps above complete
  deployment after those values and the GitHub repository are supplied.
