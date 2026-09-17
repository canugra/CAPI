import pymysql
import os
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

def run():
    db_url_str = os.getenv('DATABASE_URL')
    url = urlparse(db_url_str)
    ssl_args = {'ssl': {'ssl_verify_cert': True, 'ssl_verify_identity': True}}
    
    conn = pymysql.connect(
        host=url.hostname,
        user=url.username,
        password=url.password,
        database=url.path[1:],
        port=url.port or 4000,
        **ssl_args
    )
    
    with conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            setting_key VARCHAR(255) PRIMARY KEY,
            setting_value TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """)
    conn.commit()
    conn.close()
    print("Table system_settings created.")

if __name__ == '__main__':
    run()
