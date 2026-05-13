import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

conn = pymysql.connect(
    host=os.getenv("MYSQL_HOST", "localhost"),
    port=int(os.getenv("MYSQL_PORT", 3306)),
    user=os.getenv("MYSQL_USER", "root"),
    password=os.getenv("MYSQL_PASSWORD", "123456"),
    database=os.getenv("MYSQL_DATABASE", "movie_db"),
    charset='utf8mb4'
)

with conn.cursor() as cursor:
    cursor.execute("DESCRIBE users;")
    columns = cursor.fetchall()
    
    avatar_found = False
    for col in columns:
        if col[0] == 'avatar_url':
            avatar_found = True
            print("SUCCESS: avatar_url column already exists!")
            print(f"Type: {col[1]}")
            print(f"Default value: {col[4]}")
            
            # 查看现有用户的头像值
            cursor.execute("SELECT id, username, avatar_url FROM users LIMIT 5;")
            users = cursor.fetchall()
            print("\nSample users:")
            for u in users:
                print(f"User {u[0]} ({u[1]}): avatar = {u[2]}")
            
            break
    
    if not avatar_found:
        print("NOT FOUND: avatar_url column does not exist, adding now...")
        sql = "ALTER TABLE users ADD COLUMN avatar_url VARCHAR(255) DEFAULT 'https://movie-poster.tos-cn-guangzhou.volces.com/user-avatar/default-avatar.png';"
        cursor.execute(sql)
        conn.commit()
        print("SUCCESS: column added!")

conn.close()
