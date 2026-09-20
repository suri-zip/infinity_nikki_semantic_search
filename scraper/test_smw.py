import requests
import json
from urllib.parse import quote

API_URL = "https://wiki.biligame.com/wxnn/api.php"

query = """
[[分类:部件]]
[[实装::!未实装]]
|?名称
|?品质
|?部位
|?饰品分类
|?妆容分类
|?风格
|?标签
|?所属套装
|?新品标识
|?典雅
|?清新
|?甜美
|?性感
|?帅气
|?获取途径
|?获取途径详情
|limit=3
"""

params = {
    "action": "ask",
    "query": query,
    "format": "json"
}

response = requests.get(
    API_URL,
    params=params,
    timeout=30
)

print("status:", response.status_code)
print("url:", response.url)

data = response.json()

print(
    json.dumps(
        data,
        ensure_ascii=False,
        indent=2
    )
)