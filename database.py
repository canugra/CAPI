import os
import pymysql
import pymysql.cursors
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

def get_db():
    db_url_str = os.getenv('DATABASE_URL')
    if not db_url_str or db_url_str.startswith('sqlite'):
        raise ValueError("DATABASE_URL must be a valid TiDB/MySQL connection string (mysql+pymysql://...)")
    
    # Example format: mysql+pymysql://<user>:<password>@<host>:<port>/<dbname>?ssl_verify_cert=true&ssl_verify_identity=true
    url = urlparse(db_url_str)
    
    # TiDB requires SSL
    ssl_args = {'ssl': {'ssl_verify_cert': True, 'ssl_verify_identity': True}}
    
    conn = pymysql.connect(
        host=url.hostname,
        user=url.username,
        password=url.password,
        database=url.path[1:],
        port=url.port or 4000,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        **ssl_args
    )
    return conn

def init_db():
    print("Initializing TiDB database...")
    conn = get_db()
    with conn.cursor() as cur:
        with open('schema.sql', 'r') as f:
            sql_script = f.read()
            # Split by semicolon and execute each statement
            statements = sql_script.split(';')
            for statement in statements:
                if statement.strip():
                    cur.execute(statement)
    conn.commit()
    conn.close()
    print("TiDB Database initialized.")

if __name__ == '__main__':
    init_db()
