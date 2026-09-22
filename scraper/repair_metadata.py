import json
import time
import random
from pathlib import Path

import requests


API_URL = "https://wiki.biligame.com/wxnn/api.php"
METADATA_PATH = Path("data/raw/metadata.json")

LIMIT = 100

session = requests.Session()
session.headers.update({
    "User-Agent": "InfinityNikkiSearch/0.1"
})


def first_or_none(values):
    if not values:
        return None
    return values[0]


def parse_metadata(data):

    items = []

    for page_name, result in data["query"]["results"].items():

        p = result["printouts"]

        category = first_or_none(
            p.get("部位", [])
        )

        subcategory = None

        if category == "饰品":
            subcategory = first_or_none(
                p.get("饰品分类", [])
            )

        elif category == "妆容":
            subcategory = first_or_none(
                p.get("妆容分类", [])
            )

        rarity = first_or_none(
            p.get("品质", [])
        )

        if rarity is not None:
            try:
                rarity = int(rarity)
            except (ValueError, TypeError):
                pass

        items.append({
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
        })

    return items


def fetch_category(category):

    all_items = []
    offset = 0

    while True:

        print(
            f"[repair:{category}] "
            f"offset={offset}"
        )

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
|limit={LIMIT}
|offset={offset}
"""

        response = session.get(
            API_URL,
            params={
                "action": "ask",
                "query": query,
                "format": "json"
            },
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        page_items = parse_metadata(
            data
        )

        all_items.extend(
            page_items
        )

        next_offset = data.get(
            "query-continue-offset"
        )

        if next_offset is None:
            break

        if next_offset <= offset:
            print(
                "检测到 offset 回绕，停止。"
            )
            break

        offset = next_offset

        time.sleep(
            random.uniform(3, 5)
        )

    # 当前 repair crawl 自己也去重
    unique = {}

    for item in all_items:

        name = item.get("name")

        if name:
            unique[name] = item

    return unique


def main():

    with open(
        METADATA_PATH,
        "r",
        encoding="utf-8"
    ) as f:

        metadata = json.load(f)

    # 原数据备份
    backup_path = Path(
        "data/raw/metadata_before_repair.json"
    )

    with open(
        backup_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            metadata,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(
        f"已备份到 {backup_path}"
    )

    categories = sorted({
        item["category"]
        for item in metadata
        if item.get("category")
    })

    # 本地以 name 建索引
    local_map = {
        item["name"]: item
        for item in metadata
        if item.get("name")
    }

    total_added = 0

    for category in categories:

        print()
        print("=" * 60)
        print(f"检查 {category}")
        print("=" * 60)

        # 本地这个 category
        local_category_names = {
            item["name"]
            for item in local_map.values()
            if (
                item.get("category")
                == category
            )
        }

        # 重新请求 API
        api_map = fetch_category(
            category
        )

        api_names = set(
            api_map.keys()
        )

        missing = (
            api_names
            - local_category_names
        )

        extra = (
            local_category_names
            - api_names
        )

        print()
        print(
            f"本地: "
            f"{len(local_category_names)}"
        )

        print(
            f"本次 API: "
            f"{len(api_names)}"
        )

        print(
            f"发现缺失: "
            f"{len(missing)}"
        )

        if missing:

            print("准备补充：")

            for name in sorted(missing):

                print(
                    f"  + {name}"
                )

                # 直接使用本次 API 得到的完整 metadata
                local_map[name] = (
                    api_map[name]
                )

                total_added += 1

        if extra:

            print()
            print(
                f"本地存在但本次 API "
                f"没有的: {len(extra)}"
            )

            for name in sorted(extra):
                print(
                    f"  ? {name}"
                )

            # 注意：
            # 不自动删除这些记录！
            
        repaired = list(local_map.values())

        with open(
            METADATA_PATH,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                repaired,
                f,
                ensure_ascii=False,
                indent=2
            )

        print(
            f"已保存当前修复进度，"
            f"目前共 {len(repaired)} 条"
        )

    # --------------------------------------------------------
    # 保存修复后的 metadata
    # --------------------------------------------------------

    repaired = list(
        local_map.values()
    )

    with open(
        METADATA_PATH,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            repaired,
            f,
            ensure_ascii=False,
            indent=2
        )

    print()
    print("=" * 60)

    print(
        f"Repair 完成"
    )

    print(
        f"本次补充: "
        f"{total_added} 条"
    )

    print(
        f"最终 unique: "
        f"{len(repaired)}"
    )

    print("=" * 60)


if __name__ == "__main__":
    main()