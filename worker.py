import time
from database import get_db
from capi import send_conversion_to_meta

def process_retries():
    print("Starting background retry worker...")
    while True:
        try:
            conn = get_db()
            cur = conn.cursor()
            
            # Find conversions that need retry
            # Only retry up to 5 times (as per brief schedule conceptually)
            cur.execute("""
                SELECT order_id FROM conversion_events 
                WHERE status = 'RETRY_SCHEDULED' 
                AND attempt_count < 5
            """)
            
            events = cur.fetchall()
            for event in events:
                order_id = event['order_id']
                print(f"Retrying conversion for order_id: {order_id}")
                send_conversion_to_meta(order_id)
                
            # Fail permanently if attempts exhausted
            cur.execute("""
                UPDATE conversion_events 
                SET status = 'FAILED', last_error = 'Max retries exceeded' 
                WHERE status = 'RETRY_SCHEDULED' AND attempt_count >= 5
            """)
            conn.commit()
            
        except Exception as e:
            print("Retry worker error:", e)
            
        # Sleep for 1 minute before checking again
        time.sleep(60)

if __name__ == '__main__':
    process_retries()
