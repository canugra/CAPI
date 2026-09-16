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

# --- Middleware / Auth ---
@app.before_request
def require_login():
    allowed_routes = ['login', 'static', 'health_check', 'verify_webhook', 'receive_webhook']
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
    # Basic metrics
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as total_leads FROM leads")
    total_leads = cur.fetchone()['total_leads']
    
    cur.execute("SELECT COUNT(*) as total_orders FROM orders WHERE status='PAID'")
    total_orders = cur.fetchone()['total_orders']

    return render_template('dashboard.html', total_leads=total_leads, total_orders=total_orders)

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
    
    cur.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    lead = cur.fetchone()
    
    if not lead:
        return "Lead not found", 404
        
    cur.execute("SELECT * FROM attribution_touches WHERE lead_id = ? ORDER BY received_at DESC", (lead_id,))
    touches = cur.fetchall()
    
    cur.execute("SELECT * FROM orders WHERE lead_id = ? ORDER BY created_at DESC", (lead_id,))
    orders = cur.fetchall()
    
    # Fetch conversions for these orders
    order_ids = [str(o['id']) for o in orders]
    conversions = {}
    if order_ids:
        placeholders = ','.join('?' * len(order_ids))
        cur.execute(f"SELECT * FROM conversion_events WHERE order_id IN ({placeholders})", order_ids)
        for row in cur.fetchall():
            conversions[row['order_id']] = row
    
    cur.execute("SELECT * FROM whatsapp_messages WHERE lead_id = ? ORDER BY received_at DESC", (lead_id,))
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
            "INSERT INTO orders (order_number, lead_id, status, value, currency, paid_at, created_by) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)",
            (order_number, lead_id, 'PAID', int(value), 'IDR', session.get('username', 'admin'))
        )
        new_order_id = cur.lastrowid
        
        cur.execute("UPDATE leads SET status = 'PAID', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (lead_id,))
        
        # Log Audit
        cur.execute(
            "INSERT INTO audit_logs (actor_id, action, entity_type, entity_id) VALUES (?, ?, ?, ?)",
            (session.get('username', 'admin'), 'MARK_PAID', 'lead', str(lead_id))
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("Error marking paid:", e)
        return "Database error", 500
        
    # Trigger CAPI in the background
    import threading
    from capi import send_conversion_to_meta
    threading.Thread(target=send_conversion_to_meta, args=(new_order_id,)).start()
        
    return redirect(url_for('lead_detail', lead_id=lead_id))

@app.route('/leads/<int:lead_id>/mark-lost', methods=['POST'])
def mark_lost(lead_id):
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute("UPDATE leads SET status = 'LOST', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (lead_id,))
        cur.execute(
            "INSERT INTO audit_logs (actor_id, action, entity_type, entity_id) VALUES (?, ?, ?, ?)",
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
    cur.execute("SELECT order_id FROM conversion_events WHERE id = ?", (conversion_id,))
    conv = cur.fetchone()
    
    if conv:
        # Trigger retry in background
        import threading
        from capi import send_conversion_to_meta
        threading.Thread(target=send_conversion_to_meta, args=(conv['order_id'],)).start()
        
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
            "INSERT INTO webhook_events (provider, event_type, payload_json, status) VALUES (?, ?, ?, ?)",
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
                    cur.execute("SELECT id FROM whatsapp_messages WHERE wa_message_id = ?", (wa_message_id,))
                    if cur.fetchone():
                        continue # Already processed
                        
                    # 4. Lead Creation or Update
                    cur.execute("SELECT id, source FROM leads WHERE wa_id = ?", (wa_id,))
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
                            "INSERT INTO leads (wa_id, phone_number, customer_name, source, first_message_at, last_message_at) VALUES (?, ?, ?, ?, ?, ?)",
                            (wa_id, wa_id, customer_name, current_source, received_at, received_at)
                        )
                        lead_id = cur.lastrowid
                    else:
                        lead_id = lead['id']
                        # Upgrade source to META_AD if it was organic/unknown before
                        new_source = current_source if lead['source'] in ['UNKNOWN', 'ORGANIC'] and current_source == 'META_AD' else lead['source']
                        cur.execute(
                            "UPDATE leads SET customer_name = ?, source = ?, last_message_at = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
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
                        "INSERT INTO whatsapp_messages (lead_id, wa_message_id, direction, message_type, received_at, raw_payload_json) VALUES (?, ?, ?, ?, ?, ?)",
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
