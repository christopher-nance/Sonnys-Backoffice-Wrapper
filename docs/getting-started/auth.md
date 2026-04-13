# Authentication & Bot Setup

## Why a dedicated bot user?

- **Session stability** — a bot account isn't shared with a human whose browser session might rotate cookies mid-call.
- **Audit trail** — every action the wrapper performs is attributed to the bot user in Backoffice's audit log, not a random employee.
- **Rotation** — you can rotate the bot's password without disrupting a real person's access.

## Create the bot user

1. Log into Backoffice as an existing Administrator.
2. Navigate to **User Management → Create User**.
3. Choose "Is this user an Employee of the Wash? **No**" — the bot is an external user (standalone mode).
4. Give it a recognizable name like `Automation Bot`.
5. Set a username and a strong password.
6. Grant the **Administrator** template.
7. On the permissions page, enable **Access all Sites** (on a flat tenant) or **Available all Regions** (on a multi-region tenant). The wrapper needs full visibility to resolve site names into IDs and to reach every employee's record during disable.
8. Save.

## How the wrapper authenticates

Sonny's Backoffice runs on Symfony + PHP. The login flow is:

1. `GET /login` — fetches the login form page (no CSRF token required — Symfony trusts the session cookie).
2. `POST /login_check` with `_username` and `_password` form fields.
3. The server sets a `PHPSESSID` cookie and redirects to `/`.

The client performs this flow lazily on the first request that needs the session, and transparently re-authenticates once per request on 401/403 or if the response body re-renders the login form (which Backoffice does when the session expires).

## Store credentials safely

Never commit credentials. Use environment variables or a secret manager:

```bash
export SONNYS_SUBDOMAIN=washu
export SONNYS_BOT_USERNAME=automation-bot
export SONNYS_BOT_PASSWORD='your-strong-password-here'
```

In Python:

```python
import os

from sonnys_backoffice import SonnysBackofficeClient

client = SonnysBackofficeClient(
    subdomain=os.environ["SONNYS_SUBDOMAIN"],
    username=os.environ["SONNYS_BOT_USERNAME"],
    password=os.environ["SONNYS_BOT_PASSWORD"],
)
```

The client implements `__enter__` / `__exit__`, so the preferred pattern is:

```python
with SonnysBackofficeClient(...) as client:
    ...  # session closed automatically on exit
```
