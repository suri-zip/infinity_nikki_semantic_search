import json
import time
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

import random

METADATA_CHECKPOINT = Path(
    "data/raw/metadata_checkpoint.json"
)


API_URL = "https://wiki.biligame.com/wxnn/api.php"

OUTPUT_PATH = Path("data/raw/items.json")

LIMIT = 3

session = requests.Session()

session.headers.update({
    "User-Agent": "InfinityNikkiSearch/0.1"
})


# ============================================================
# 通用工具
# ============================================================

def first_or_none(values):
    if not values:
        return None

    return values[0]


def get_original_image_url(img):
    src = img.get("src")

    if not src:
        return None

    # MediaWiki thumbnail:
    #
    # /images/wxnn/thumb/a/ab/file.png/85px-name.png
    #
    # 原图:
    #
    # /images/wxnn/a/ab/file.png

    if "/thumb/" in src:
        before, after = src.split("/thumb/", 1)
        parts = after.split("/")

        original_path = "/".join(parts[:-1])

        return before + "/" + original_path

    return src


# ============================================================
# 1. Semantic MediaWiki metadata
# ============================================================

def fetch_metadata_page(offset=0, limit=LIMIT, max_retries=5):

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

    for attempt in range(max_retries):

        try:
            response = session.get(
                API_URL,
                params=params,
                timeout=30
            )

            response.raise_for_status()

            return response.json()

        except requests.RequestException as e:

            print(
                f"  请求失败 "
                f"(offset={offset}, "
                f"第 {attempt + 1}/{max_retries} 次): "
                f"{e}"
            )

            if attempt == max_retries - 1:
                raise

            wait_time = 2 ** attempt

            print(
                f"  等待 {wait_time} 秒后重试..."
            )

            time.sleep(wait_time)

def parse_metadata(data):

    results = data["query"]["results"]

    items = []

    for _, result in results.items():

        p = result["printouts"]

        category = first_or_none(
            p.get("部位", [])
        )

        # ---------- 二级分类 ----------

        subcategory = None

        if category == "饰品":
            subcategory = first_or_none(
                p.get("饰品分类", [])
            )

        elif category == "妆容":
            subcategory = first_or_none(
                p.get("妆容分类", [])
            )

        # ---------- 品质 ----------

        rarity = first_or_none(
            p.get("品质", [])
        )

        if rarity is not None:
            try:
                rarity = int(rarity)
            except ValueError:
                pass

        # ---------- item ----------

        item = {
            "name": first_or_none(
                p.get("名称", [])
            ),

            "rarity": rarity,

            "category": category,

            "subcategory": subcategory,

            "game_style": first_or_none(
                p.get("风格", [])
            ),

            "tags": p.get(
                "标签",
                []
            ),

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

            "wiki_url": result.get(
                "fullurl"
            )
        }

        items.append(item)

    return items


def fetch_all_metadata():

    all_items = load_checkpoint()

    offset = len(all_items)

    if all_items:
        print(
            f"发现 checkpoint："
            f"{len(all_items)} 条"
        )
        print(
            f"从 offset={offset} 继续"
        )


    while True:

        print(f"[metadata] offset={offset}")

        data = fetch_metadata_page(
            offset=offset
        )

        items = parse_metadata(data)

        all_items.extend(items)

        # 每成功一页立即保存
        save_checkpoint(all_items)

        print(
            f"  获取 {len(items)} 条，"
            f"累计 {len(all_items)} 条"
        )

        next_offset = data.get(
            "query-continue-offset"
        )

        if next_offset is None:
            break

        offset = next_offset

        wait = random.uniform(3, 6)

        print(
            f"  等待 {wait:.1f} 秒..."
        )

        time.sleep(wait)

    return all_items


# ============================================================
# 2. 获取图片
# ============================================================

def fetch_image_page(offset=0, limit=LIMIT):

    query = f"""
{{{{#ask:
[[分类:部件]]
[[实装::!未实装]]
|?名称
|?品质
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

    response = session.get(
        API_URL,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    return data["parse"]["text"]["*"]


def parse_images(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    cards = soup.select(
        "div.lbbj"
    )

    items = []

    for card in cards:

        name_link = card.select_one(
            'a[title^="部件"]'
        )

        if not name_link:
            continue

        title = name_link.get(
            "title",
            ""
        )

        name = title.removeprefix(
            "部件"
        )

        item_image_url = None
        worn_image_url = None

        container = card.select_one(
            ".smw-highlighter"
        )

        if container:

            for img in container.select("img"):

                alt = img.get(
                    "alt",
                    ""
                )

                src = get_original_image_url(
                    img
                )

                if alt.endswith("01.png"):
                    item_image_url = src

                elif alt.endswith("02.jpg"):
                    worn_image_url = src

        items.append({
            "name": name,
            "item_image_url": item_image_url,
            "worn_image_url": worn_image_url
        })

    return items


def fetch_all_images():

    all_images = []

    offset = 0

    while True:

        print(f"[images] offset={offset}")

        html = fetch_image_page(
            offset=offset
        )

        images = parse_images(html)

        all_images.extend(images)

        print(
            f"  获取 {len(images)} 条，"
            f"累计 {len(all_images)} 条"
        )

        # 最后一页不足 LIMIT
        if len(images) < LIMIT:
            break

        offset += LIMIT

        time.sleep(0.5)

    return all_images

def save_checkpoint(items):
    METADATA_CHECKPOINT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        METADATA_CHECKPOINT,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            items,
            f,
            ensure_ascii=False,
            indent=2
        )


def load_checkpoint():
    if not METADATA_CHECKPOINT.exists():
        return []

    with open(
        METADATA_CHECKPOINT,
        "r",
        encoding="utf-8"
    ) as f:
        return json.load(f)


# ============================================================
# 3. 合并 metadata + images
# ============================================================

def merge_items(metadata, images):

    image_map = {
        item["name"]: item
        for item in images
    }

    merged = []

    for item in metadata:

        name = item["name"]

        image_data = image_map.get(
            name,
            {}
        )

        item["item_image_url"] = (
            image_data.get(
                "item_image_url"
            )
        )

        item["worn_image_url"] = (
            image_data.get(
                "worn_image_url"
            )
        )

        merged.append(item)

    return merged


# ============================================================
# 4. 简单检查
# ============================================================

def validate_items(items):

    missing_item_images = []
    missing_worn_images = []
    missing_names = []

    for item in items:

        if not item["name"]:
            missing_names.append(item)

        if not item["item_image_url"]:
            missing_item_images.append(
                item["name"]
            )

        if not item["worn_image_url"]:
            missing_worn_images.append(
                item["name"]
            )

    print()
    print("========== 数据检查 ==========")

    print(
        "总部件:",
        len(items)
    )

    print(
        "缺少名称:",
        len(missing_names)
    )

    print(
        "缺少单品图:",
        len(missing_item_images)
    )

    print(
        "缺少穿着图:",
        len(missing_worn_images)
    )

    if missing_item_images:
        print(
            "单品图缺失示例:",
            missing_item_images[:10]
        )

    if missing_worn_images:
        print(
            "穿着图缺失示例:",
            missing_worn_images[:10]
        )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print("开始获取 metadata...")

    metadata = fetch_all_metadata()

    print()
    print("开始获取图片...")

    images = fetch_all_images()

    print()
    print("开始合并...")

    items = merge_items(
        metadata,
        images
    )

    validate_items(items)

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            items,
            f,
            ensure_ascii=False,
            indent=2
        )

    print()
    print(
        f"完成：{len(items)} 件部件"
    )

    print(
        f"保存至：{OUTPUT_PATH}"
    )