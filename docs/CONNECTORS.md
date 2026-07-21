# Connecting Word, PowerPoint, Excel and Figma

Domain → **Documentation → Apps** shows your real files from these apps, and
lets you edit Word/Excel/PowerPoint in place and write the changes back.

Two registrations cover everything:

| App | Registration | Editable in AURA |
|---|---|---|
| Word, PowerPoint, Excel | one **Microsoft 365** app | yes — changes save back |
| Figma | one **Figma** app | read-only (Figma's API has no write surface) |

Python packages (`python-docx`, `openpyxl`, `python-pptx`, `lxml`) are already
installed in `venv/`. Nothing else to install.

---

## 1. Microsoft 365 — covers Word, PowerPoint and Excel

1. Go to <https://portal.azure.com> → search **App registrations** → **New registration**.
2. **Name:** `AURA Domain` (anything you like).
3. **Supported account types:** *Accounts in any organizational directory and personal Microsoft accounts* — this is the one that works with both a personal @outlook.com account and a work/school account.
4. **Redirect URI:** choose platform **Web** and enter exactly:

   ```
   http://localhost:8760/api/connectors/callback/microsoft
   ```

   > Azure's portal refuses `http://127.0.0.1` in this box — see the note at the
   > bottom if the callback page fails to load.

5. **Register.** Copy the **Application (client) ID** from the overview page.
6. **Certificates & secrets** → **New client secret** → copy the **Value**
   (not the Secret ID — the value is only shown once).
7. **API permissions** → **Add a permission** → **Microsoft Graph** →
   **Delegated permissions**, and add:

   - `Files.ReadWrite.All` — open and save your documents
   - `Sites.Read.All` — reach files stored in SharePoint / Teams
   - `User.Read` — label the connected account
   - `offline_access` — stay signed in without re-authorising daily

   Then click **Grant admin consent** if that button is available to you. On a
   personal account it isn't needed — you'll approve at sign-in instead.

8. In AURA: **Domain → Settings → Connectors → Microsoft 365**, paste the client
   ID and secret, **Save credentials**, then **Connect** and sign in.

Word, PowerPoint and Excel all light up together — they're one connector.

---

## 2. Figma

1. Go to <https://www.figma.com/developers/apps> → **Create a new app**.
2. **Name:** `AURA Domain`.
3. **Callback URL:**

   ```
   http://localhost:8760/api/connectors/callback/figma
   ```

4. Copy the **client ID** and **client secret**.
5. Figma now requires OAuth apps to be **published** before third-party sign-in
   works. On the app page, publish it (private/for-your-team is fine) — an
   unpublished app returns *"this app doesn't exist"* at the authorise step.
6. In AURA: **Settings → Connectors → Figma**, paste both values, **Save**, then
   **Connect**.

### Figma team IDs

Figma's API has no "list all my files" endpoint — files are reached through
teams. In the same connector card, paste your **team IDs**, comma separated.

Find one by opening the team in Figma; the URL looks like:

```
https://www.figma.com/files/team/1234567890123456789/…
                                 ^^^^^^^^^^^^^^^^^^^ this is the team ID
```

---

## 3. Where credentials live

Either place works — the database wins if both are set:

- **Domain → Settings → Connectors** — stored in AURA's local SQLite database
- **`.env`** — `MS_CLIENT_ID`, `MS_CLIENT_SECRET`, `FIGMA_CLIENT_ID`, `FIGMA_CLIENT_SECRET`

Access and refresh tokens are always stored in the database and refreshed
automatically. **Disconnect** clears them.

---

## Troubleshooting

**"Needs credentials" on the card**
The client ID or secret is empty. Paste both, then Save.

**Azure: "The redirect URI specified in the request does not match"**
The URI must match character for character, including the port and no trailing
slash. Copy it straight from the connector card in Settings.

**The callback page won't load after signing in**
Your browser resolved `localhost` to IPv6 (`::1`) and AURA's bridge only listens
on `127.0.0.1`. Two fixes, either works:

- *Preferred:* in Azure, **Manifest** → find `replyUrlsWithType` → change the URL
  to `http://127.0.0.1:8760/api/connectors/callback/microsoft` and save. The
  portal blocks this in the UI but the manifest accepts it.
- *Or:* keep `localhost` in Azure and add `AURA_BRIDGE_ORIGIN=http://localhost:8760`
  to `.env`, so AURA asks for the same host you registered.

**Figma: "this app doesn't exist"**
The app isn't published yet. Publish it on the Figma app page.

**"python-docx not installed"**
The bridge is running from a different Python than `venv/`. Start AURA with
`AURA.bat`, or install into whichever interpreter runs `server.py`:

```
venv\Scripts\python -m pip install -r requirements-web.txt
```

**A file opens but won't save**
Files opened from someone else's SharePoint need write access on their side.
Read-only files fail at save with the message Graph returns.
