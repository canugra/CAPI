import re

files = ['app.py', 'capi.py', 'worker.py']

for file_path in files:
    with open(file_path, 'r') as f:
        content = f.read()

    # Find cur.execute(..., (...)) and replace ? with %s inside the string literal
    # A simple approach: we know where the ? are for SQL bindings in our code.
    
    # Let's replace ? with %s where it's not part of an HTTP URL
    lines = content.split('\n')
    new_lines = []
    for line in lines:
        if 'cur.execute' in line or 'INSERT' in line or 'UPDATE' in line or 'SELECT' in line or 'IN (' in line:
            if 'http' not in line:
                line = line.replace('?', '%s')
        new_lines.append(line)
        
    with open(file_path, 'w') as f:
        f.write('\n'.join(new_lines))
        
print("Replaced ? with %s in SQL queries")
