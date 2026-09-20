import requests
from sympy import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json

API_URL = "https://wiki.biligame.com/wxnn/api.php"
BASE_URL = "https://wiki.biligame.com"

def fetch_page(offset=0, limit=36):
    query = f"""
{{{{#ask:
[[分类:部件]]
[[实装::!未实装]]
|?名称
|?品质
|?部位
|?饰品分类
|?妆容分类
|?风格
|?标签
|?新品标识
|?所属套装
|template=部件图鉴/行
|headers=hide
|format=template
|link=none
|named args=1
|sort=列表排序
|order=desc
|limit={limit}
|offset={offset}
}}}}
"""

    params = {
        "format": "json",
        "action": "parse",
        "text": query,
        "contentmodel": "wikitext"
    }

    response = requests.get(
        API_URL,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    return data["parse"]["text"]["*"]


def parse_items(html):
    soup = BeautifulSoup(html, "html.parser")

    items = []

    cards = soup.select("div.lbbj")

    print(f"找到 {len(cards)} 个卡片")

    print(cards[0].prettify())

    for card in cards:

        # ---------- 名称 ----------
        name_link = card.select_one('a[title^="部件"]')

        if not name_link:
            continue

        title = name_link.get("title", "")
        name = title.removeprefix("部件")

        detail_url = urljoin(
            BASE_URL,
            name_link.get("href", "")
        )

        # ---------- 图片 ----------
        image_container = card.select_one(".smw-highlighter")

        item_image_url = None
        worn_image_url = None

        if image_container:
            images = image_container.select("img")

            for img in images:
                alt = img.get("alt", "")
                src = get_best_image_url(img)

                if alt.endswith("01.png"):
                    item_image_url = src

                elif alt.endswith("02.jpg"):
                    worn_image_url = src

        # ---------- 游戏风格 ----------
        style_element = card.select_one("span.tjsx")

        game_style = (
            style_element.get_text(strip=True)
            if style_element
            else None
        )

        # ---------- 标签 ----------
        tags = [
            tag.get_text(strip=True)
            for tag in card.select("span.tjbq")
            if tag.get_text(strip=True)
        ]

        # ---------- 品质 / 星级 ----------
        rarity = None

        rarity_img = card.select_one(
            '.floatright img[alt*="星ICON"]'
        )

        if rarity_img:
            alt = rarity_img.get("alt", "")

            match = re.search(r"(\d+)星", alt)

            if match:
                rarity = int(match.group(1))


        # ---------- 所属套装 ----------
        outfit_set = None

        rarity_container = card.select_one(".floatright")

        if rarity_container:
            parent = rarity_container.parent
            outfit_span = parent.find("span", recursive=False)

            if outfit_span:
                text = outfit_span.get_text(strip=True)

                if text:
                    outfit_set = text

        # ---------- 新品 ----------
        new_icon = card.select_one(
            '.new img[alt="NewIcon.png"]'
        )

        is_new = new_icon is not None

        items.append({
            "name": name,
            "rarity": rarity,
            "game_style": game_style,
            "tags": tags,
            "outfit_set": outfit_set,
            "is_new": is_new,
            "wiki_url": detail_url,
            "item_image_url": item_image_url,
            "worn_image_url": worn_image_url
        })


    return items

def get_best_image_url(img):
    srcset = img.get("srcset")

    if srcset:
        candidates = srcset.split(",")

        # srcset 最后一个通常是最高分辨率
        best = candidates[-1].strip().split(" ")[0]

        return best

    return img.get("src")


def first_or_none(values):
    if not values:
        return None
    return values[0]


def parse_metadata(data):
    results = data["query"]["results"]

    items = []

    for page_name, result in results.items():
        p = result["printouts"]

        category = first_or_none(p.get("部位", []))

        # 二级分类
        subcategory = None

        if category == "饰品":
            subcategory = first_or_none(
                p.get("饰品分类", [])
            )

        elif category == "妆容":
            subcategory = first_or_none(
                p.get("妆容分类", [])
            )

        item = {
            "name": first_or_none(p.get("名称", [])),
            "rarity": first_or_none(p.get("品质", [])),
            "category": category,
            "subcategory": subcategory,
            "game_style": first_or_none(p.get("风格", [])),
            "tags": p.get("标签", []),
            "outfit_set": first_or_none(
                p.get("所属套装", [])
            ),
            "is_new": bool(
                p.get("新品标识", [])
            ),
            "acquisition": first_or_none(
                p.get("获取途径", [])
            ),
            "acquisition_detail": first_or_none(
                p.get("获取途径详情", [])
            ),
            "wiki_url": result.get("fullurl")
        }

        # 品质转成 int
        if item["rarity"] is not None:
            try:
                item["rarity"] = int(item["rarity"])
            except ValueError:
                pass

        items.append(item)

    return items


def fetch_metadata(offset=0, limit=100):
    query = f"""
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
|sort=列表排序
|order=desc
|limit={limit}
|offset={offset}
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

    response.raise_for_status()

    return response.json()

"""

if __name__ == "__main__":

    html = fetch_page(offset=0)

    items = parse_items(html)

    for item in items[:10]:
        print("=" * 50)
        print("名称:", item["name"])
        print("详情:", item["wiki_url"])
        print("单品图:", item["item_image_url"])
        print("穿着图:", item["worn_image_url"])

        """

if __name__ == "__main__":
    data = fetch_metadata(
        offset=0,
        limit=3
    )

    items = parse_metadata(data)

    print(
        json.dumps(
            items,
            ensure_ascii=False,
            indent=2
        )
    )