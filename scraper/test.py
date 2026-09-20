import requests

API_URL = "https://wiki.biligame.com/wxnn/api.php"

query = """
{{#ask:
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
|?获取途径
|?获取途径详情
|format=csv
|limit=3
|offset=0
}}
"""

params = {
    "action": "parse",
    "text": query,
    "contentmodel": "wikitext",
    "format": "json"
}

response = requests.get(
    API_URL,
    params=params,
    timeout=30
)

print("status:", response.status_code)

if response.ok:
    data = response.json()
    print(data["parse"]["text"]["*"])
else:
    print(response.text[:1000])