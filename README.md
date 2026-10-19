# CoreCloud

A complete HR &amp; Payroll portal built with Django.

## Features
- Employee management (add, edit, delete)
- Attendance tracking (clock in/out)
- Leave management (apply, approve/reject)
- Auto payroll generation from attendance + leave data
- Salary slips (PDF export)
- Payroll policies (configurable deductions, bonuses, tax)
- HR modules: training, travel, overtime, documents, announcements, IT help desk
- Collaboration: internal mail, chat and meetings
- Reports &amp; analytics dashboards (light/dark theme)
- Security Operations Center (SOC / SIEM): security event stream, detection
  rules with alerts, incident triage and automated response (auto-lock,
  session revocation, IT ticket, notification)

## Security Operations Center (SOC)

The `soc` app turns the audit trail into a lightweight SIEM/SOC:

- **Events**: logins (success/failure), lockouts/unlocks, face logins, CRUD,
  authorize/deauthorize, CSV exports and response actions are written to
  `AuditLog` with severity, outcome, category, user agent and path.
- **Detection**: 9 seeded rules (brute force, credential stuffing, suspicious
  IP, mass export, off-hours admin, privilege change, IP switch, locked-account
  attempts, account lockout) evaluate inline on every event.
- **Alerts**: fingerprinted and de-duplicated, with ack/close/escalate actions.
- **Response**: critical rules with `auto_response` run playbooks — lock the
  account, revoke sessions, open a password-reset ticket, notify Networks.
- **Incidents**: escalate alerts into incidents with status workflow, notes,
  team/assignee.
- **Dashboard**: `/soc/` with Chart.js volume/rule/IP/actor charts and a live
  event feed (10s polling).

Access is gated by new permission tokens: `view_soc` / `respond_soc` (IT support
staff and IT managers) and `manage_soc` (IT managers, superusers).

```bash
# Seed rules + scan the last 24h (also runs automatically on every event)
python manage.py run_soc_rules

# Local dev daemon: rescan every 5 minutes
python manage.py run_soc_rules --loop --interval 300
```

Production re-scan runs daily via the Vercel cron (`/cron/soc/`, guarded by
`CRON_SECRET`). Detection is primarily inline — every audit event is evaluated
in real time, so the cron is just a safety-net sweep.

## Deployment to Vercel

### Step 1: Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/hr-payroll-system.git
git push -u origin main
```

### Step 2: Deploy on Vercel
1. Go to https://vercel.com
2. Sign up with GitHub
3. Click "New Project"
4. Import your GitHub repository
5. Click "Deploy"

The project is built by `api/index.py` (WSGI entry point). Static files are
served from the committed `staticfiles/` directory via `vercel.json`, so run
`python manage.py collectstatic --noinput` and commit `staticfiles/` whenever
`static/` assets change.

`runtime.txt` pins the Python version. Django 6 requires Python 3.12+.

### Step 3: Set Environment Variables
Set these in your Vercel project settings (and never commit them to Git):

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Django secret key (generate one and keep it secret) |
| `DEBUG` | `False` in production |
| `DATABASE_URL` | Full Postgres connection string, e.g. `postgres://user:pass@host/db` |
| `SEED_DEMO` | `True` only to load the demo org chart once |
| `CRON_SECRET` | Secret for the `/cron/soc/` SOC scan endpoint (used by the Vercel cron) |

Optional but recommended for password reset emails:
`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`.

Optional SOC settings:
| Variable | Purpose |
| --- | --- |
| `SOC_AUTO_RESPONSE` | `False` to disable auto-lock/session-revoke playbooks |
| `SOC_CRON_SECRET` | Alternative to `CRON_SECRET` for `/cron/soc/?secret=...` |

> Rotate any database password that has ever been committed to a public repository.

### Step 4: Access Your Site
- Your site will be at: `https://your-project.vercel.app`
- Any active employee can log in with their `employee_id` / default password (they are prompted to change it on first login).

## Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Seed sample data (standalone script)
python seed_data.py

# Collect static files
python manage.py collectstatic --noinput

# Run server
python manage.py runserver
```

## Project Structure
```
hr-payroll-system/
|- hr_payroll/          # Project settings, URLs, context processors
|- employees/           # Employee module + auth, slides, face login
|- attendance/          # Attendance module
|- leaves/              # Leave module
|- payroll/             # Payroll module (incl. PDF slips)
|- hr_modules/          # Training, travel, overtime, documents, help desk
|- collab/              # Internal mail, chat, meetings
|- ai_engine/           # Insights / risk helpers
|- soc/                 # SOC/SIEM: events, rules, alerts, incidents, response
|- templates/           # HTML templates
|- static/              # Source CSS/JS
|- staticfiles/         # Collected static assets (committed for Vercel)
|- api/                 # Vercel WSGI entry point
|- vercel.json          # Vercel config
|- requirements.txt     # Python dependencies
|- runtime.txt          # Python version
```
