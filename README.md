# Quickmeal WhatsApp → Meta CAPI System

This system connects Quickmeal's WhatsApp leads to Meta Conversions API (CAPI) for accurate tracking of Click-to-WhatsApp ads.

## Architecture
- **Language:** Python 3 (Flask)
- **Database:** SQLite (with WAL mode for high concurrency)
- **Frontend:** Server-Side Rendered HTML + Tailwind CSS
- **Dependencies:** Minimal (`flask`, `requests`, `python-dotenv`)

## Deployment Guide (Production Hardening)

To launch this system securely on a production server (VPS like DigitalOcean, AWS, etc.):

### 1. Server Setup
1. Clone this repository to your Linux server (Ubuntu recommended).
2. Install Python 3 and Nginx:
   ```bash
   sudo apt update
   sudo apt install python3-venv python3-pip nginx
   ```

### 2. Application Setup
1. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Initialize the database:
   ```bash
   python database.py
   ```

### 3. Environment Variables
1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Edit `.env` with your **REAL** production secrets:
   - `SESSION_SECRET`: Generate a strong random string.
   - `META_ACCESS_TOKEN`: The permanent access token from your Meta Developer App.
   - `META_WABA_ID`: WhatsApp Business Account ID.
   - `WHATSAPP_VERIFY_TOKEN`: A secret string you will input into the Meta Developer Dashboard for webhook verification.

### 4. Running as a Service (Gunicorn & Systemd)
Do not use `start_dashboard.bat` or `app.run` in production. Use a WSGI server like Gunicorn.
1. Install Gunicorn:
   ```bash
   pip install gunicorn
   ```
2. Create a Systemd service file (`/etc/systemd/system/quickmeal.service`):
   ```ini
   [Unit]
   Description=Gunicorn instance to serve Quickmeal CAPI
   After=network.target

   [Service]
   User=www-data
   Group=www-data
   WorkingDirectory=/path/to/META CAPI
   Environment="PATH=/path/to/META CAPI/venv/bin"
   ExecStart=/path/to/META CAPI/venv/bin/gunicorn --workers 3 --bind unix:quickmeal.sock -m 007 wsgi:app

   [Install]
   WantedBy=multi-user.target
   ```
   *(Note: You will need to create a simple `wsgi.py` file containing `from app import app`)*
3. Enable and start the service:
   ```bash
   sudo systemctl start quickmeal
   sudo systemctl enable quickmeal
   ```

### 5. Background Worker (Retry Queue)
To ensure failed CAPI events are retried automatically, run `worker.py` in the background.
Create another Systemd service (`/etc/systemd/system/quickmeal-worker.service`):
```ini
[Unit]
Description=Quickmeal CAPI Retry Worker
After=network.target

[Service]
WorkingDirectory=/path/to/META CAPI
ExecStart=/path/to/META CAPI/venv/bin/python worker.py
Restart=always

[Install]
WantedBy=multi-user.target
```
Enable it: `sudo systemctl start quickmeal-worker`

### 6. Reverse Proxy & HTTPS (Nginx + Certbot)
Meta **requires** a secure `https://` endpoint for Webhooks.
1. Configure Nginx to proxy requests to Gunicorn's socket.
2. Install Certbot to generate a free SSL certificate:
   ```bash
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx -d yourdomain.com
   ```
3. Your Meta Webhook URL will be: `https://yourdomain.com/api/webhooks/whatsapp`

### 7. Database Backups
Since this uses SQLite, the database is a single file (`quickmeal.db`).
Setup a simple cron job to back this file up daily:
```bash
0 2 * * * cp /path/to/META\ CAPI/quickmeal.db /path/to/backups/quickmeal_$(date +\%F).db
```

## End-to-End Meta Testing
Once deployed to your `https://` domain:
1. Go to your Meta Developer App -> WhatsApp -> Configuration.
2. Click **Edit Webhook**, enter your domain `https://.../api/webhooks/whatsapp` and your `WHATSAPP_VERIFY_TOKEN`.
3. Subscribe to the `messages` field.
4. Click an actual Click-to-WhatsApp ad on your phone.
5. Send a message.
6. Open your new Quickmeal Dashboard and verify the lead appears with `META_AD` source.
7. Click **Mark as Paid**.
8. Verify in the Meta Events Manager that the Purchase event was received!
