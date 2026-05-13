import os
import pymysql
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 数据库配置
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "123456")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "movie_db")

# SQL语句
ALTER_SQL = """
ALTER TABLE users 
ADD COLUMN avatar_url VARCHAR(255) 
DEFAULT 'https://movie-poster.tos-cn-guangzhou.volces.com/user-avatar/default-avatar.png';
"""

def main():
    try:
        # 连接数据库
        conn = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            charset='utf8mb4'
        )
        
        with conn.cursor() as cursor:
            # 执行SQL
            cursor.execute(ALTER_SQL)
            conn.commit()
            print("✅ 字段添加成功！")
            
            # 验证结果
            cursor.execute("DESCRIBE users;")
            columns = cursor.fetchall()
            for col in columns:
                if col[0] == 'avatar_url':
                    print(f"\n📋 字段信息：")
                    print(f"字段名：{col[0]}")
                    print(f"类型：{col[1]}")
                    print(f"默认值：{col[4]}")
                    break
            
        conn.close()
        print("\n✅ 执行完成！所有用户已自动分配默认头像。")
        
    except Exception as e:
        print(f"❌ 执行失败：{str(e)}")
        if "Duplicate column name" in str(e):
            print("ℹ️ 提示：avatar_url 字段已经存在，无需重复添加。")

if __name__ == "__main__":
    main()
