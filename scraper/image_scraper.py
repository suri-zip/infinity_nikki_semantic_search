import json
import random
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIG
# ============================================================

API_URL = "https://wiki.biligame.com/wxnn/api.php"
BASE_URL = "https://wiki.biligame.com"

IMAGE_LIMIT = 12

MIN_WAIT = 4
MAX_WAIT = 7

# metadata scraper 生成的最终文件
METADATA_PATH = Path(
    "data/raw/metadata.json"
)

# 每个 category 的图片 checkpoint
CHECKPOINT_DIR = Path(
    "data/raw/image_checkpoints"
)

# 最终图片 URL 数据
OUTPUT_PATH = Path(
    "data/raw/images.json"
)

# 最终 metadata + image 合并结果
MERGED_OUTPUT_PATH = Path(
    "data/raw/items.json"
)


# ============================================================
# SESSION
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": "InfinityNikkiSearch/0.1"
})


# ============================================================
# HELPERS
# ============================================================

def safe_filename(name):

    invalid_chars = '<>:"/\\|?*'

    for char in invalid_chars:
        name = name.replace(char, "_")

    return name


def get_original_image_url(img):
    """
    把 MediaWiki thumbnail URL 转成原图 URL。

    例如：

    /thumb/a/ab/xxx.png/170px-xxx.png

    ->

    /a/ab/xxx.png
    """

    if img is None:
        return None

    src = img.get("src")

    if not src:
        return None

    # 补全 https://wiki.biligame.com
    src = urljoin(
        BASE_URL,
        src
    )

    if "/thumb/" not in src:
        return src

    before, after = src.split(
        "/thumb/",
        1
    )

    parts = after.split("/")

    # 最后一段是 thumbnail 文件名
    if len(parts) < 2:
        return src

    original_path = "/".join(
        parts[:-1]
    )

    return (
        before
        + "/"
        + original_path
    )


# ============================================================
# LOAD METADATA
# ============================================================

def load_metadata():

    if not METADATA_PATH.exists():

        raise FileNotFoundError(
            f"找不到 metadata："
            f"{METADATA_PATH}"
        )

    with open(
        METADATA_PATH,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


def get_categories(metadata):

    return sorted({
        item.get("category")
        for item in metadata
        if item.get("category")
    })


# ============================================================
# FETCH IMAGE PAGE
# ============================================================

def fetch_image_page(
    category,
    offset=0,
    limit=IMAGE_LIMIT
):

    query = f"""
{{{{#ask:
[[分类:部件]]
[[实装::!未实装]]
[[部位::{category}]]
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

    if response.status_code != 200:

        raise requests.HTTPError(
            f"HTTP {response.status_code}: "
            f"{response.reason}",
            response=response
        )

    data = response.json()

    return data["parse"]["text"]["*"]


# ============================================================
# PARSE IMAGE HTML
# ============================================================

def parse_images(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    cards = soup.select(
        "div.lbbj"
    )

    results = []

    for card in cards:

        # ----------------------------------------------------
        # NAME
        # ----------------------------------------------------

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
        ).strip()

        if not name:
            continue

        # ----------------------------------------------------
        # ITEM IMAGE: 01.png
        # ----------------------------------------------------

        item_image_url = None

        item_img = card.select_one(
            'img[alt$="01.png"]'
        )

        if item_img:

            # 排除施工.jpg placeholder
            alt = item_img.get(
                "alt",
                ""
            )

            if alt != "施工.jpg":

                item_image_url = (
                    get_original_image_url(
                        item_img
                    )
                )

        # ----------------------------------------------------
        # WORN IMAGE: 02.jpg
        # ----------------------------------------------------

        worn_image_url = None

        worn_img = card.select_one(
            '.smwttcontent img[alt$="02.jpg"]'
        )

        if worn_img:

            worn_image_url = (
                get_original_image_url(
                    worn_img
                )
            )

        # ----------------------------------------------------
        # RESULT
        # ----------------------------------------------------

        results.append({
            "name": name,
            "item_image_url": item_image_url,
            "worn_image_url": worn_image_url
        })

    return results


# ============================================================
# CHECKPOINT
# ============================================================

def get_checkpoint_path(category):

    return (
        CHECKPOINT_DIR
        / f"{safe_filename(category)}.json"
    )


def load_checkpoint(category):

    path = get_checkpoint_path(
        category
    )

    if not path.exists():

        return {
            "category": category,
            "next_offset": 0,
            "complete": False,
            "items": []
        }

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


def save_checkpoint(
    category,
    items,
    next_offset,
    complete
):

    CHECKPOINT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    path = get_checkpoint_path(
        category
    )

    data = {
        "category": category,
        "next_offset": next_offset,
        "complete": complete,
        "items": items
    }

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# DEDUP
# ============================================================

def deduplicate(items):

    unique = {}

    for item in items:

        name = item.get("name")

        if name:
            unique[name] = item

    return list(
        unique.values()
    )


# ============================================================
# FETCH ONE CATEGORY
# ============================================================

def fetch_category_images(
    category,
    expected_names
):

    checkpoint = load_checkpoint(
        category
    )

    if checkpoint.get(
        "complete",
        False
    ):

        items = checkpoint.get(
            "items",
            []
        )

        print(
            f"[{category}] "
            f"图片已经完成："
            f"{len(items)} 条"
        )

        return items

    items = checkpoint.get(
        "items",
        []
    )

    offset = checkpoint.get(
        "next_offset",
        0
    )

    if offset is None:
        offset = 0

    print()
    print("=" * 60)

    print(
        f"开始图片抓取：{category}"
    )

    print(
        f"metadata 中预计："
        f"{len(expected_names)} 条"
    )

    print(
        f"checkpoint 已有："
        f"{len(items)} 条"
    )

    print(
        f"从 offset={offset} 开始"
    )

    print("=" * 60)

    while True:

        print(
            f"[image:{category}] "
            f"offset={offset}"
        )

        try:

            html = fetch_image_page(
                category=category,
                offset=offset,
                limit=IMAGE_LIMIT
            )

        except requests.RequestException as e:

            print(
                f"请求失败：{e}"
            )

            save_checkpoint(
                category,
                items,
                offset,
                False
            )

            raise

        page_items = parse_images(
            html
        )

        # ----------------------------------------------------
        # 没数据了
        # ----------------------------------------------------

        if not page_items:

            print(
                "没有更多图片记录。"
            )

            save_checkpoint(
                category,
                items,
                None,
                True
            )

            break

        # ----------------------------------------------------
        # merge
        # ----------------------------------------------------

        items.extend(
            page_items
        )

        items = deduplicate(
            items
        )

        print(
            f"  本页 {len(page_items)} 条，"
            f"累计 {len(items)} 条"
        )

        # ----------------------------------------------------
        # 如果已经达到 metadata 数量
        # ----------------------------------------------------

        names_found = {
            item["name"]
            for item in items
        }

        if expected_names.issubset(
            names_found
        ):

            print(
                f"[{category}] "
                "已覆盖 metadata 中全部部件。"
            )

            save_checkpoint(
                category,
                items,
                None,
                True
            )

            break

        # ----------------------------------------------------
        # 最后一页
        # ----------------------------------------------------

        if len(page_items) < IMAGE_LIMIT:

            print(
                f"[{category}] "
                "到达最后一页。"
            )

            save_checkpoint(
                category,
                items,
                None,
                True
            )

            break

        # ----------------------------------------------------
        # next offset
        # ----------------------------------------------------

        next_offset = (
            offset
            + IMAGE_LIMIT
        )

        # 保险
        if next_offset <= offset:

            raise RuntimeError(
                f"offset 异常："
                f"{offset} -> "
                f"{next_offset}"
            )

        # ----------------------------------------------------
        # checkpoint BEFORE sleep
        # ----------------------------------------------------

        save_checkpoint(
            category,
            items,
            next_offset,
            False
        )

        offset = next_offset

        wait = random.uniform(
            MIN_WAIT,
            MAX_WAIT
        )

        print(
            f"  等待 {wait:.1f} 秒..."
        )

        time.sleep(wait)

    return items


# ============================================================
# MERGE IMAGE CHECKPOINTS
# ============================================================

def merge_images(categories):

    all_images = []

    for category in categories:

        checkpoint = load_checkpoint(
            category
        )

        items = checkpoint.get(
            "items",
            []
        )

        print(
            f"{category}: "
            f"{len(items)} image records"
        )

        all_images.extend(
            items
        )

    return deduplicate(
        all_images
    )


# ============================================================
# VALIDATE IMAGES
# ============================================================

def validate_images(
    metadata,
    images
):

    metadata_names = {
        item["name"]
        for item in metadata
        if item.get("name")
    }

    image_names = {
        item["name"]
        for item in images
        if item.get("name")
    }

    missing_records = (
        metadata_names
        - image_names
    )

    extra_records = (
        image_names
        - metadata_names
    )

    missing_item_image = [
        item["name"]
        for item in images
        if not item.get(
            "item_image_url"
        )
    ]

    missing_worn_image = [
        item["name"]
        for item in images
        if not item.get(
            "worn_image_url"
        )
    ]

    print()
    print("=" * 60)
    print("IMAGE VALIDATION")
    print("=" * 60)

    print(
        f"metadata 部件数: "
        f"{len(metadata_names)}"
    )

    print(
        f"image record 数: "
        f"{len(image_names)}"
    )

    print(
        f"缺少 image record: "
        f"{len(missing_records)}"
    )

    print(
        f"额外 image record: "
        f"{len(extra_records)}"
    )

    print(
        f"缺少 01.png: "
        f"{len(missing_item_image)}"
    )

    print(
        f"缺少 02.jpg: "
        f"{len(missing_worn_image)}"
    )

    if missing_records:

        print()
        print(
            "缺少记录示例："
        )

        for name in sorted(
            missing_records
        )[:20]:

            print(
                f"  - {name}"
            )


# ============================================================
# MERGE METADATA + IMAGE
# ============================================================

def merge_metadata_images(
    metadata,
    images
):

    image_map = {
        item["name"]: item
        for item in images
        if item.get("name")
    }

    merged = []

    for item in metadata:

        new_item = item.copy()

        image_data = image_map.get(
            item.get("name"),
            {}
        )

        new_item[
            "item_image_url"
        ] = image_data.get(
            "item_image_url"
        )

        new_item[
            "worn_image_url"
        ] = image_data.get(
            "worn_image_url"
        )

        merged.append(
            new_item
        )

    return merged


# ============================================================
# SAVE JSON
# ============================================================

def save_json(
    path,
    data
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# MAIN
# ============================================================

def main():

    metadata = load_metadata()

    categories = get_categories(
        metadata
    )

    print(
        f"metadata 共 "
        f"{len(metadata)} 条"
    )

    print(
        f"共 {len(categories)} "
        f"个 category"
    )

    # --------------------------------------------------------
    # 每个 category
    # --------------------------------------------------------

    for category in categories:

        expected_names = {
            item["name"]
            for item in metadata
            if (
                item.get("category")
                == category
                and item.get("name")
            )
        }

        try:

            fetch_category_images(
                category,
                expected_names
            )

        except Exception as e:

            print()
            print(
                f"图片抓取中断：{e}"
            )

            print(
                "checkpoint 已保存。"
            )

            print(
                "下次重新运行即可继续。"
            )

            return

    # --------------------------------------------------------
    # merge image checkpoints
    # --------------------------------------------------------

    images = merge_images(
        categories
    )

    save_json(
        OUTPUT_PATH,
        images
    )

    # --------------------------------------------------------
    # validate
    # --------------------------------------------------------

    validate_images(
        metadata,
        images
    )

    # --------------------------------------------------------
    # metadata + images
    # --------------------------------------------------------

    merged = (
        merge_metadata_images(
            metadata,
            images
        )
    )

    save_json(
        MERGED_OUTPUT_PATH,
        merged
    )

    print()
    print("=" * 60)

    print(
        f"images.json: "
        f"{OUTPUT_PATH}"
    )

    print(
        f"最终 items.json: "
        f"{MERGED_OUTPUT_PATH}"
    )

    print("=" * 60)


if __name__ == "__main__":
    main()