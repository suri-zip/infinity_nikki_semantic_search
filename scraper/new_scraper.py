import json
import random
import time
from pathlib import Path

import requests


# ============================================================
# CONFIG
# ============================================================

API_URL = "https://wiki.biligame.com/wxnn/api.php"

# 现在先保持 3。
# 稳定以后可以改成 5 / 10。
LIMIT = 3

MIN_WAIT = 3
MAX_WAIT = 6

# 你之前已经抓出来的 checkpoint
OLD_CHECKPOINT_PATH = Path(
    "data/raw/metadata_checkpoint.json"
)

# 每个 category 单独保存
CHECKPOINT_DIR = Path(
    "data/raw/checkpoints"
)

# 最终 metadata
OUTPUT_PATH = Path(
    "data/raw/metadata.json"
)


# ============================================================
# SESSION
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": "InfinityNikkiSearch/0.1"
})


# ============================================================
# BASIC HELPERS
# ============================================================

def first_or_none(values):
    if not values:
        return None

    return values[0]


def safe_filename(name):
    """
    把 category 转成安全的文件名。
    中文本身可以正常作为 Windows 文件名。
    """

    invalid_chars = '<>:"/\\|?*'

    for char in invalid_chars:
        name = name.replace(char, "_")

    return name


# ============================================================
# PARSE METADATA
# ============================================================

def parse_metadata(data):

    results = data["query"]["results"]

    items = []

    for _, result in results.items():

        p = result["printouts"]

        category = first_or_none(
            p.get("部位", [])
        )

        # --------------------
        # subcategory
        # --------------------

        subcategory = None

        if category == "饰品":
            subcategory = first_or_none(
                p.get("饰品分类", [])
            )

        elif category == "妆容":
            subcategory = first_or_none(
                p.get("妆容分类", [])
            )

        # --------------------
        # rarity
        # --------------------

        rarity = first_or_none(
            p.get("品质", [])
        )

        if rarity is not None:
            try:
                rarity = int(rarity)
            except (ValueError, TypeError):
                pass

        # --------------------
        # item
        # --------------------

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


# ============================================================
# API
# ============================================================

def fetch_metadata_page(
    category,
    offset=0,
    limit=LIMIT
):

    query = f"""
[[分类:部件]]
[[实装::!未实装]]
[[部位::{category}]]
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

    response = session.get(
        API_URL,
        params=params,
        timeout=30
    )

    # 不疯狂 retry。
    # 如果被 567，就保存现状退出，
    # 以后重新运行继续。
    if response.status_code != 200:

        raise requests.HTTPError(
            f"HTTP {response.status_code}: "
            f"{response.reason}",
            response=response
        )

    return response.json()


# ============================================================
# OLD CHECKPOINT
# ============================================================

def load_old_items():

    if not OLD_CHECKPOINT_PATH.exists():
        return []

    print(
        f"发现旧 checkpoint："
        f"{OLD_CHECKPOINT_PATH}"
    )

    with open(
        OLD_CHECKPOINT_PATH,
        "r",
        encoding="utf-8"
    ) as f:

        data = json.load(f)

    # 支持：
    #
    # [
    #   {...},
    #   {...}
    # ]
    #
    # 以及：
    #
    # {
    #   "next_offset": ...,
    #   "items": [...]
    # }

    if isinstance(data, list):
        items = data

    elif isinstance(data, dict):
        items = data.get(
            "items",
            []
        )

    else:
        items = []

    print(
        f"旧 checkpoint 中有 "
        f"{len(items)} 条记录"
    )

    return items


# ============================================================
# FIND CATEGORIES
# ============================================================

def get_categories_from_old_data():

    items = load_old_items()

    categories = sorted({
        item.get("category")
        for item in items
        if item.get("category")
    })

    return categories


# ============================================================
# CATEGORY CHECKPOINT
# ============================================================

def get_checkpoint_path(category):

    filename = (
        safe_filename(category)
        + ".json"
    )

    return CHECKPOINT_DIR / filename


def load_category_checkpoint(category):

    path = get_checkpoint_path(category)

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

        data = json.load(f)

    return data


def save_category_checkpoint(
    category,
    items,
    next_offset,
    complete=False
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
# DEDUPLICATION
# ============================================================

def deduplicate_items(items):

    unique = {}

    for item in items:

        name = item.get("name")

        if not name:
            continue

        # 同名时保留最后一次
        unique[name] = item

    return list(
        unique.values()
    )


# ============================================================
# FETCH ONE CATEGORY
# ============================================================

def fetch_category(category):

    checkpoint = (
        load_category_checkpoint(
            category
        )
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
            f"已经完成，"
            f"共 {len(items)} 条"
        )

        return items

    all_items = checkpoint.get(
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
        f"开始抓取 category: "
        f"{category}"
    )

    print(
        f"已有 {len(all_items)} 条"
    )

    print(
        f"从 offset={offset} 继续"
    )

    print("=" * 60)

    while True:

        print(
            f"[{category}] "
            f"offset={offset}"
        )

        try:

            data = fetch_metadata_page(
                category=category,
                offset=offset,
                limit=LIMIT
            )

        except (
            requests.RequestException,
            requests.HTTPError
        ) as e:

            print()
            print(
                f"[{category}] "
                f"请求失败：{e}"
            )

            print(
                "当前进度已经保存。"
            )

            print(
                "停止本次抓取。"
            )

            # 保证最后状态落盘
            save_category_checkpoint(
                category=category,
                items=all_items,
                next_offset=offset,
                complete=False
            )

            raise

        # --------------------
        # parse
        # --------------------

        items = parse_metadata(
            data
        )

        # API 如果突然返回空
        if not items:

            print(
                f"[{category}] "
                f"没有更多数据。"
            )

            save_category_checkpoint(
                category=category,
                items=all_items,
                next_offset=None,
                complete=True
            )

            break

        all_items.extend(
            items
        )

        all_items = (
            deduplicate_items(
                all_items
            )
        )

        # --------------------
        # next offset
        # --------------------

        next_offset = data.get(
            "query-continue-offset"
        )

        print(
            f"  获取 {len(items)} 条，"
            f"该分类累计 "
            f"{len(all_items)} 条"
        )

        # --------------------
        # finished
        # --------------------

        if next_offset is None:

            save_category_checkpoint(
                category=category,
                items=all_items,
                next_offset=None,
                complete=True
            )

            print(
                f"[{category}] "
                f"完成，共 "
                f"{len(all_items)} 条"
            )

            break

        # --------------------
        # 防止 offset 回绕
        # --------------------

        if next_offset <= offset:

            print()
            print(
                "!!! 检测到分页回绕 !!!"
            )

            print(
                f"category={category}"
            )

            print(
                f"current offset={offset}"
            )

            print(
                f"next offset={next_offset}"
            )

            save_category_checkpoint(
                category=category,
                items=all_items,
                next_offset=offset,
                complete=False
            )

            raise RuntimeError(
                f"{category} 分页发生回绕："
                f"{offset} -> "
                f"{next_offset}"
            )

        # --------------------
        # checkpoint
        # --------------------

        save_category_checkpoint(
            category=category,
            items=all_items,
            next_offset=next_offset,
            complete=False
        )

        offset = next_offset

        # --------------------
        # polite delay
        # --------------------

        wait = random.uniform(
            MIN_WAIT,
            MAX_WAIT
        )

        print(
            f"  等待 {wait:.1f} 秒..."
        )

        time.sleep(wait)

    return all_items


# ============================================================
# MERGE ALL CATEGORY CHECKPOINTS
# ============================================================

def merge_all_checkpoints(
    categories
):

    all_items = []

    print()
    print("=" * 60)
    print("合并所有 category")
    print("=" * 60)

    for category in categories:

        checkpoint = (
            load_category_checkpoint(
                category
            )
        )

        items = checkpoint.get(
            "items",
            []
        )

        complete = checkpoint.get(
            "complete",
            False
        )

        print(
            f"{category}: "
            f"{len(items)} 条 "
            f"complete={complete}"
        )

        all_items.extend(
            items
        )

    before = len(
        all_items
    )

    all_items = (
        deduplicate_items(
            all_items
        )
    )

    after = len(
        all_items
    )

    print()
    print(
        f"合并前记录数: {before}"
    )

    print(
        f"唯一部件数: {after}"
    )

    print(
        f"删除重复数: "
        f"{before - after}"
    )

    return all_items


# ============================================================
# VALIDATION
# ============================================================

def validate_metadata(items):

    print()
    print("=" * 60)
    print("DATA VALIDATION")
    print("=" * 60)

    names = [
        item.get("name")
        for item in items
        if item.get("name")
    ]

    print(
        f"总记录数: "
        f"{len(items)}"
    )

    print(
        f"唯一名称数: "
        f"{len(set(names))}"
    )

    print(
        f"缺少名称: "
        f"{sum(1 for x in items if not x.get('name'))}"
    )

    print(
        f"缺少 category: "
        f"{sum(1 for x in items if not x.get('category'))}"
    )

    print(
        f"缺少 rarity: "
        f"{sum(1 for x in items if x.get('rarity') is None)}"
    )

    print(
        f"缺少 game_style: "
        f"{sum(1 for x in items if not x.get('game_style'))}"
    )

    # --------------------
    # category distribution
    # --------------------

    counts = {}

    for item in items:

        category = (
            item.get("category")
            or "UNKNOWN"
        )

        counts[category] = (
            counts.get(category, 0)
            + 1
        )

    print()
    print("Category 分布:")

    for category, count in sorted(
        counts.items(),
        key=lambda x: x[1],
        reverse=True
    ):

        print(
            f"  {category}: {count}"
        )


# ============================================================
# SAVE FINAL
# ============================================================

def save_final_metadata(items):

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
        f"最终 metadata 已保存："
    )

    print(
        OUTPUT_PATH
    )


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # 1. 从旧的 5000+ 数据里自动找 category
    # --------------------------------------------------------

    categories = (
        get_categories_from_old_data()
    )

    if not categories:

        print(
            "没有从旧 checkpoint "
            "找到任何 category。"
        )

        print(
            "请检查："
        )

        print(
            OLD_CHECKPOINT_PATH
        )

        return

    print()
    print(
        "发现以下 category："
    )

    for category in categories:
        print(
            f"  - {category}"
        )

    print()
    print(
        f"共 {len(categories)} 个 category"
    )

    # --------------------------------------------------------
    # 2. 每个 category 单独爬
    # --------------------------------------------------------

    for category in categories:

        try:

            fetch_category(
                category
            )

        except Exception as e:

            print()
            print("=" * 60)

            print(
                f"抓取中断：{e}"
            )

            print(
                "checkpoint 已保存。"
            )

            print(
                "下次重新运行本程序"
                "即可继续。"
            )

            print("=" * 60)

            return

    # --------------------------------------------------------
    # 3. 合并
    # --------------------------------------------------------

    metadata = (
        merge_all_checkpoints(
            categories
        )
    )

    # --------------------------------------------------------
    # 4. 检查
    # --------------------------------------------------------

    validate_metadata(
        metadata
    )

    # --------------------------------------------------------
    # 5. 保存
    # --------------------------------------------------------

    save_final_metadata(
        metadata
    )

    print()
    print("=" * 60)

    print(
        "METADATA 抓取完成"
    )

    print("=" * 60)


if __name__ == "__main__":
    main()