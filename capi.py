import os
import json
import time
import requests
from datetime import datetime
from database import get_db

def send_conversion_to_meta(order_id):
    """
    Constructs and sends a Purchase event to Meta CAPI.
    This should be called in a background thread after an order is marked PAID.
    """
    conn = get_db()
    cur = conn.cursor()
    
    # 1. Fetch Order
    cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
    order = cur.fetchone()
    if not order or order['status'] != 'PAID':
        return
        
    lead_id = order['lead_id']
    
    # 2. Check if a conversion record already exists for this order
    cur.execute("SELECT id, status FROM conversion_events WHERE order_id = %s AND event_name = 'Purchase'", (order_id,))
    existing_event = cur.fetchone()
    
    if existing_event and existing_event['status'] == 'SUCCESS':
        # Idempotency: Do not resend successful conversions
        return
        
    # 3. Find latest eligible attribution touch
    cur.execute("SELECT ctwa_clid FROM attribution_touches WHERE lead_id = %s AND ctwa_clid IS NOT NULL ORDER BY received_at DESC LIMIT 1", (lead_id,))
    touch = cur.fetchone()
    
    if not touch:
        # Not attributable to a Meta ad
        if not existing_event:
            cur.execute(
                """INSERT INTO conversion_events 
                (order_id, platform, event_name, event_id, ctwa_clid, status, created_at) 
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                (order_id, 'META', 'Purchase', f"qm_purch_{order['order_number']}", None, 'NOT_ATTRIBUTABLE')
            )
            conn.commit()
        return

    ctwa_clid = touch['ctwa_clid']
    event_id = f"qm_purch_{order['order_number']}"
    event_time = int(datetime.strptime(order['paid_at'], "%Y-%m-%d %H:%M:%S").timestamp()) if order['paid_at'] else int(time.time())
    
    if not existing_event:
        cur.execute(
            """INSERT INTO conversion_events 
            (order_id, platform, event_name, event_id, ctwa_clid, event_time, value, currency, status, created_at) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (order_id, 'META', 'Purchase', event_id, ctwa_clid, datetime.utcfromtimestamp(event_time).strftime('%Y-%m-%d %H:%M:%S'), order['value'], order['currency'], 'PENDING')
        )
        conversion_id = cur.lastrowid
        conn.commit()
    else:
        conversion_id = existing_event['id']

    # 4. Prepare Meta CAPI Payload
    payload = {
        "data": [
            {
                "event_name": "Purchase",
                "event_time": event_time,
                "event_id": event_id,
                "action_source": "business_messaging",
                "messaging_channel": "whatsapp",
                "user_data": {
                    "ctwa_clid": ctwa_clid
                },
                "custom_data": {
                    "value": order['value'],
                    "currency": order['currency']
                }
            }
        ]
    }
    
    # Update attempt
    cur.execute("UPDATE conversion_events SET status = 'SENDING', attempt_count = attempt_count + 1, last_attempt_at = CURRENT_TIMESTAMP WHERE id = %s", (conversion_id,))
    conn.commit()
    
    access_token = os.getenv('META_ACCESS_TOKEN')
    waba_id = os.getenv('META_WABA_ID')
    api_version = os.getenv('META_GRAPH_API_VERSION', 'v19.0')
    
    if not access_token or not waba_id:
        cur.execute("UPDATE conversion_events SET status = 'FAILED', last_error = 'Missing Meta Credentials' WHERE id = %s", (conversion_id,))
        conn.commit()
        return

    # 5. Send to Meta Graph API
    url = f"https://graph.facebook.com/{api_version}/{waba_id}/events"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        http_status = response.status_code
        response_json = response.text
        
        if http_status == 200:
            status = 'SUCCESS'
        elif http_status in [429, 500, 502, 503, 504]:
            status = 'RETRY_SCHEDULED'
        else:
            status = 'FAILED' # Permanent errors like 400, 401, 403
            
        cur.execute(
            """UPDATE conversion_events 
            SET status = ?, http_status = ?, provider_response_json = ?, sent_at = CURRENT_TIMESTAMP 
            WHERE id = ?""",
            (status, http_status, response_json, conversion_id)
        )
        conn.commit()
        
    except requests.exceptions.RequestException as e:
        # Network errors are retryable
        cur.execute(
            "UPDATE conversion_events SET status = 'RETRY_SCHEDULED', last_error = %s WHERE id = %s",
            (str(e), conversion_id)
        )
        conn.commit()
    except Exception as e:
        cur.execute(
            "UPDATE conversion_events SET status = 'FAILED', last_error = %s WHERE id = %s",
            (str(e), conversion_id)
        )
        conn.commit()
