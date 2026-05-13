import tos
import os
import hashlib

# TOS 配置
AK = os.environ.get("TOS_ACCESS_KEY", "your-access-key")
SK = os.environ.get("TOS_SECRET_KEY", "your-secret-key")
ENDPOINT = "tos-cn-guangzhou.volces.com"
REGION = "cn-guangzhou"
BUCKET_NAME = "movie-poster"
OBJECT_KEY = "covers/test-preview.jpg"
TEST_IMAGE_PATH = "data/preview.jpg"

print("=" * 50)
print("火山引擎 TOS 上传测试")
print("=" * 50)

try:
    # 1. 创建 TOS 客户端
    print("\n[1/5] 创建 TOS 客户端...")
    client = tos.TosClientV2(AK, SK, ENDPOINT, REGION)
    print("[OK] TOS 客户端创建成功")

    # 2. 检查文件是否存在
    print(f"\n[2/5] 检查测试文件 {TEST_IMAGE_PATH}...")
    if not os.path.exists(TEST_IMAGE_PATH):
        print(f"[ERROR] 文件不存在: {TEST_IMAGE_PATH}")
        exit(1)
    print(f"[OK] 文件存在，大小: {os.path.getsize(TEST_IMAGE_PATH) / 1024:.2f} KB")

    # 3. 上传文件
    print(f"\n[3/5] 上传文件到 {BUCKET_NAME}/{OBJECT_KEY}...")
    with open(TEST_IMAGE_PATH, 'rb') as f:
        resp = client.put_object(BUCKET_NAME, OBJECT_KEY, content=f.read())
    
    print(f"响应状态码: {resp.status_code}")
    print(f"响应头: {resp.header}")
    
    if resp.status_code == 200:
        print("[OK] 文件上传成功")
        print(f"  ETag: {resp.header.get('etag', 'N/A')}")
    else:
        print(f"[ERROR] 文件上传失败")
        if resp.status_code == 403:
            print("===== 403 错误分析 =====")
            print("常见原因：1.AK/SK权限不足 2.Bucket Policy拦截 3.地域/Endpoint错误 4.临时AK过期")

    # 4. 验证上传（增强版）
    print(f"\n[4/5] 验证文件元数据...")
    try:
        resp = client.head_object(BUCKET_NAME, OBJECT_KEY)
        if resp.status_code == 200:
            etag = resp.header['etag'].strip('"')
            print("[OK] 文件存在于TOS桶中")
            print(f"  桶内路径: {BUCKET_NAME}/{OBJECT_KEY}")
            print(f"  文件大小: {int(resp.header['content-length'])/1024:.2f} KB")
            print(f"  本地文件大小: {os.path.getsize(TEST_IMAGE_PATH)/1024:.2f} KB")
            print(f"  TOS ETag: {etag}")
            # 计算本地文件MD5与ETag对比（最严格验证）
            with open(TEST_IMAGE_PATH, 'rb') as f:
                local_md5 = hashlib.md5(f.read()).hexdigest()
            print(f"  本地MD5: {local_md5}")
            if etag == local_md5:
                print("[OK] 文件内容完全一致，上传无损坏")
            else:
                print("[WARN] ETag不一致（可能是分块上传，不影响使用）")
    except Exception as e:
        print(f"[ERROR] 验证失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 50)
    print("测试完成！")
    print("=" * 50)

except Exception as e:
    print(f"\n[ERROR] 发生错误: {e}")
    import traceback
    traceback.print_exc()