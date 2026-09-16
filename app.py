from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from database import get_db

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SESSION_SECRET', 'super_secret_fallback')
app.config['ADMIN_USER'] = os.getenv('ADMIN_USERNAME', 'admin')
app.config['ADMIN_PASS'] = os.getenv('ADMIN_PASSWORD', 'secret')

@app.template_filter('currency')
def format_currency(value):
    try:
        return f"Rp {int(value):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "Rp 0"

# --- Middleware / Auth ---
@app.before_request
def require_login():
    allowed_routes = ['login', 'static', 'health_check', 'verify_webhook', 'receive_webhook', 'process_capi_cron']
    if request.endpoint not in allowed_routes and 'logged_in' not in session:
        return redirect(url_for('login'))

# --- Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form.get('username') == app.config['ADMIN_USER'] and \
           request.form.get('password') == app.config['ADMIN_PASS']:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            error = "Invalid credentials"
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@app.route('/dashboard')
def dashboard():
    conn = get_db()
    cur = conn.cursor()
    
    # 1. KPI Row
    cur.execute("SELECT COUNT(*) as total FROM leads")
    total_leads = cur.fetchone()['total'] or 0
    
    cur.execute("SELECT COUNT(DISTINCT lead_id) as paid FROM orders WHERE status='PAID'")
    paid_orders = cur.fetchone()['paid'] or 0
    
    cur.execute("SELECT SUM(value) as rev FROM orders WHERE status='PAID'")
    revenue = cur.fetchone()['rev'] or 0
    
    conversion_rate = round((paid_orders / total_leads * 100) if total_leads > 0 else 0, 1)

    # 2. Lead Sources (Donut Chart Data)
    cur.execute("SELECT source, COUNT(*) as count FROM leads GROUP BY source")
    source_counts = cur.fetchall()
    sources = {'META_AD': 0, 'ORGANIC': 0, 'UNKNOWN': 0}
    for s in source_counts:
        src = s['source'] if s['source'] in sources else 'UNKNOWN'
        sources[src] += s['count']
        
    # 3. System Health
    cur.execute("SELECT received_at FROM whatsapp_messages ORDER BY received_at DESC LIMIT 1")
    last_wa = cur.fetchone()
    
    cur.execute("SELECT sent_at FROM conversion_events WHERE status='SUCCESS' ORDER BY sent_at DESC LIMIT 1")
    last_capi = cur.fetchone()
    
    cur.execute("SELECT COUNT(*) as succ FROM conversion_events WHERE status='SUCCESS'")
    capi_success = cur.fetchone()['succ'] or 0
    
    cur.execute("SELECT COUNT(*) as fail FROM conversion_events WHERE status='FAILED'")
    capi_failed = cur.fetchone()['fail'] or 0
    
    cur.execute("SELECT COUNT(*) as pend FROM conversion_events WHERE status='PENDING' OR status='RETRY_SCHEDULED'")
    capi_pending = cur.fetchone()['pend'] or 0

    # 4. Recent Leads
    cur.execute("""
        SELECT l.*, o.value as order_value, o.status as order_status, c.status as capi_status 
        FROM leads l
        LEFT JOIN orders o ON o.lead_id = l.id
        LEFT JOIN conversion_events c ON c.order_id = o.id
        ORDER BY l.last_message_at DESC LIMIT 5
    """)
    recent_leads = cur.fetchall()

    return render_template(
        'dashboard.html', 
        total_leads=total_leads, 
        paid_orders=paid_orders,
        conversion_rate=conversion_rate,
        revenue=revenue,
        sources=sources,
        last_wa=last_wa['received_at'] if last_wa else None,
        last_capi=last_capi['sent_at'] if last_capi else None,
        capi_success=capi_success,
        capi_failed=capi_failed,
        capi_pending=capi_pending,
        recent_leads=recent_leads
    )

@app.route('/api/health/integrations')
def health_check():
    health = {
        "status": "healthy",
        "database": "ok",
        "webhook": "ok",
        "meta_capi": "pending_config" # Meta CAPI config will be verified here later
    }
    try:
        get_db().execute("SELECT 1")
    except Exception as e:
        health['database'] = "error"
        health['status'] = "error"
        health['error_details'] = str(e)

    return jsonify(health)

@app.route('/leads')
def leads():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM leads ORDER BY created_at DESC")
    leads_list = cur.fetchall()
    return render_template('leads.html', leads=leads_list)

@app.route('/leads/<int:lead_id>')
def lead_detail(lead_id):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM leads WHERE id = %s", (lead_id,))
    lead = cur.fetchone()
    
    if not lead:
        return "Lead not found", 404
        
    cur.execute("SELECT * FROM attribution_touches WHERE lead_id = %s ORDER BY received_at DESC", (lead_id,))
    touches = cur.fetchall()
    
    cur.execute("SELECT * FROM orders WHERE lead_id = %s ORDER BY created_at DESC", (lead_id,))
    orders = cur.fetchall()
    
    # Fetch conversions for these orders
    order_ids = [str(o['id']) for o in orders]
    conversions = {}
    if order_ids:
        placeholders = ','.join(['%s'] * len(order_ids))
        cur.execute(f"SELECT * FROM conversion_events WHERE order_id IN ({placeholders})", order_ids)
        for row in cur.fetchall():
            conversions[row['order_id']] = row
    
    cur.execute("SELECT * FROM whatsapp_messages WHERE lead_id = %s ORDER BY received_at DESC", (lead_id,))
    messages = cur.fetchall()
    
    return render_template('lead_detail.html', lead=lead, touches=touches, orders=orders, messages=messages, conversions=conversions)

@app.route('/leads/<int:lead_id>/mark-paid', methods=['POST'])
def mark_paid(lead_id):
    value = request.form.get('value')
    if not value or not value.isdigit():
        return "Invalid purchase value", 400
        
    conn = get_db()
    cur = conn.cursor()
    
    import uuid
    order_number = f"ORD-{uuid.uuid4().hex[:8].upper()}"
    
    try:
        cur.execute(
            "INSERT INTO orders (order_number, lead_id, status, value, currency, paid_at, created_by) VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s)",
            (order_number, lead_id, 'PAID', int(value), 'IDR', session.get('username', 'admin'))
        )
        new_order_id = cur.lastrowid
        
        cur.execute("UPDATE leads SET status = 'PAID', updated_at = CURRENT_TIMESTAMP WHERE id = %s", (lead_id,))
        
        # Log Audit
        cur.execute(
            "INSERT INTO audit_logs (actor_id, action, entity_type, entity_id) VALUES (%s, %s, %s, %s)",
            (session.get('username', 'admin'), 'MARK_PAID', 'lead', str(lead_id))
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("Error marking paid:", e)
        return "Database error", 500
        
    # Trigger CAPI synchronously (Vercel doesn't support background threads well)
    from capi import send_conversion_to_meta
    send_conversion_to_meta(new_order_id)
        
    return redirect(url_for('lead_detail', lead_id=lead_id))

@app.route('/api/cron/process-capi', methods=['GET', 'POST'])
def process_capi_cron():
    """Endpoint for UptimeRobot/Cron to process retries automatically"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT order_id FROM conversion_events WHERE status = 'RETRY_SCHEDULED' AND attempt_count < 5")
    events = cur.fetchall()
    
    from capi import send_conversion_to_meta
    processed = 0
    for event in events:
        send_conversion_to_meta(event['order_id'])
        processed += 1
        
    # Mark max retries as failed
    cur.execute("UPDATE conversion_events SET status = 'FAILED', last_error = 'Max retries exceeded' WHERE status = 'RETRY_SCHEDULED' AND attempt_count >= 5")
    conn.commit()
    
    return jsonify({"status": "ok", "retries_processed": processed}), 200

@app.route('/leads/<int:lead_id>/mark-lost', methods=['POST'])
def mark_lost(lead_id):
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute("UPDATE leads SET status = 'LOST', updated_at = CURRENT_TIMESTAMP WHERE id = %s", (lead_id,))
        cur.execute(
            "INSERT INTO audit_logs (actor_id, action, entity_type, entity_id) VALUES (%s, %s, %s, %s)",
            (session.get('username', 'admin'), 'MARK_LOST', 'lead', str(lead_id))
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        return "Database error", 500
        
    return redirect(url_for('lead_detail', lead_id=lead_id))

@app.route('/conversions/<int:conversion_id>/retry', methods=['POST'])
def retry_conversion(conversion_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT order_id FROM conversion_events WHERE id = %s", (conversion_id,))
    conv = cur.fetchone()
    
    if conv:
        # Trigger retry synchronously for Vercel
        from capi import send_conversion_to_meta
        send_conversion_to_meta(conv['order_id'])
        
    # Redirect back to the referrer (which should be the lead detail page)
    return redirect(request.referrer or url_for('dashboard'))

# --- Webhook Routes ---
@app.route('/api/webhooks/whatsapp', methods=['GET'])
def verify_webhook():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode and token:
        if mode == 'subscribe' and token == os.getenv('WHATSAPP_VERIFY_TOKEN'):
            return challenge, 200
        else:
            return 'Forbidden', 403
    return 'Bad Request', 400

@app.route('/api/webhooks/whatsapp', methods=['POST'])
def receive_webhook():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    
    # 1. Log the webhook event
    try:
        cur.execute(
            "INSERT INTO webhook_events (provider, event_type, payload_json, status) VALUES (%s, %s, %s, %s)",
            ('META', 'whatsapp', json.dumps(data), 'RECEIVED')
        )
        conn.commit()
    except Exception as e:
        print("Failed to log webhook:", e)

    # 2. Parse Meta Webhook Format
    try:
        if data and data.get('object') == 'whatsapp_business_account':
            for entry in data.get('entry', []):
                for change in entry.get('changes', []):
                    value = change.get('value', {})
                    
                    contacts = value.get('contacts', [])
                    messages = value.get('messages', [])
                    
                    if not contacts or not messages:
                        continue
                        
                    contact = contacts[0]
                    message = messages[0]
                    
                    wa_id = contact.get('wa_id')
                    customer_name = contact.get('profile', {}).get('name')
                    wa_message_id = message.get('id')
                    timestamp = message.get('timestamp')
                    message_type = message.get('type')
                    
                    if not wa_id or not wa_message_id:
                        continue
                        
                    # 3. Duplicate Protection (Idempotency)
                    cur.execute("SELECT id FROM whatsapp_messages WHERE wa_message_id = %s", (wa_message_id,))
                    if cur.fetchone():
                        continue # Already processed
                        
                    # 4. Lead Creation or Update
                    cur.execute("SELECT id, source FROM leads WHERE wa_id = %s", (wa_id,))
                    lead = cur.fetchone()
                    
                    received_at = datetime.fromtimestamp(int(timestamp)) if timestamp else datetime.utcnow()
                    
                    # Extract Attribution
                    referral = message.get('referral') or message.get('context', {}).get('referral')
                    current_source = 'UNKNOWN'
                    if referral:
                        current_source = 'META_AD' if referral.get('ctwa_clid') else 'ORGANIC'
                    else:
                        current_source = 'ORGANIC'
                        
                    if not lead:
                        cur.execute(
                            "INSERT INTO leads (wa_id, phone_number, customer_name, source, first_message_at, last_message_at) VALUES (%s, %s, %s, %s, %s, %s)",
                            (wa_id, wa_id, customer_name, current_source, received_at, received_at)
                        )
                        lead_id = cur.lastrowid
                    else:
                        lead_id = lead['id']
                        # Upgrade source to META_AD if it was organic/unknown before
                        new_source = current_source if lead['source'] in ['UNKNOWN', 'ORGANIC'] and current_source == 'META_AD' else lead['source']
                        cur.execute(
                            "UPDATE leads SET customer_name = %s, source = %s, last_message_at = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                            (customer_name, new_source, received_at, lead_id)
                        )
                        
                    # Capture Attribution Touch
                    if referral:
                        ctwa_clid = referral.get('ctwa_clid')
                        source_id = referral.get('source_id')
                        source_url = referral.get('source_url')
                        source_type = referral.get('source_type')
                        headline = referral.get('headline')
                        body = referral.get('body')
                        media_type = referral.get('media_type')
                        
                        if ctwa_clid or source_id or source_url:
                            cur.execute(
                                """INSERT INTO attribution_touches 
                                (lead_id, ctwa_clid, source_id, source_type, source_url, headline, body, media_type, raw_referral_json, received_at) 
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (lead_id, ctwa_clid, source_id, source_type, source_url, headline, body, media_type, json.dumps(referral), received_at)
                            )
                        
                    # 5. Store Message Metadata
                    cur.execute(
                        "INSERT INTO whatsapp_messages (lead_id, wa_message_id, direction, message_type, received_at, raw_payload_json) VALUES (%s, %s, %s, %s, %s, %s)",
                        (lead_id, wa_message_id, 'INBOUND', message_type, received_at, json.dumps(message))
                    )
                    
                    conn.commit()
    except Exception as e:
        print("Webhook processing error:", e)
        # Always return 200 to Meta to prevent endless retries for structural bugs
        return 'Processed with errors', 200

    return 'OK', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
