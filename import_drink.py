import re
import sqlite3
from models import get_db, init_db

DRINK_FILE = 'drink.md'

def parse_drink():
    with open(DRINK_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    drink_shops = []
    current_shop = None
    current_category = None
    for line in lines:
        line = line.strip()
        if line.startswith('# ') and '飲料店菜單' in line:
            current_shop = line.replace('# ', '').replace(' 飲料店菜單', '').strip()
            drink_shops.append({'name': current_shop, 'categories': []})
        elif line.startswith('## '):
            current_category = line.replace('## ', '').strip()
            if current_shop:
                drink_shops[-1]['categories'].append({'name': current_category, 'items': []})
        elif line.startswith('- '):
            # 品項與價格
            m = re.match(r'- (.+?)\s*[.。．…]*\s*([0-9]+)(/\S+)?', line)
            if m and current_shop and current_category:
                item_name = m.group(1).strip()
                price = int(m.group(2))
                note = m.group(3).strip() if m.group(3) else None
                drink_shops[-1]['categories'][-1]['items'].append({'name': item_name, 'price': price, 'note': note})
    return drink_shops

def get_drinkshop_prefix(name):
    # 取飲料店拼音首字母，特殊例外可自行擴充
    mapping = {
        '鶴茶樓': 'H',
        '50嵐': 'W',
        '麻古飲料店': 'M',
        '水巷茶弄': 'S',
        '三分春色': 'F',
        '清原': 'Q',
        '得正': 'D',
    }
    return mapping.get(name, name[0].upper())

def gen_alpha2(n):
    # n: 0-based, return AA, AB, ..., AZ, BA, ..., ZZ
    return chr(65 + n // 26) + chr(65 + n % 26)

def assign_restaurant_codes():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id FROM restaurant ORDER BY id')
    ids = [row['id'] for row in c.fetchall()]
    for idx, rid in enumerate(ids):
        code = gen_alpha2(idx)
        c.execute('UPDATE restaurant SET code=? WHERE id=?', (code, rid))
    conn.commit()
    conn.close()

def import_to_db(drink_shops):
    conn = get_db()
    c = conn.cursor()
    # 先插入所有飲料店
    for shop in drink_shops:
        c.execute('INSERT OR IGNORE INTO restaurant (name) VALUES (?)', (shop['name'],))
    conn.commit()
    assign_restaurant_codes()
    # 重新查一次 name->(id,code)
    c.execute('SELECT id, name, code FROM restaurant')
    shop_map = {row['name']: (row['id'], row['code']) for row in c.fetchall()}
    for shop in drink_shops:
        shop_id, shop_code = shop_map[shop['name']]
        item_counter = 1
        for cat in shop['categories']:
            c.execute('INSERT INTO menu_category (restaurant_id, name) VALUES (?, ?)', (shop_id, cat['name']))
            category_id = c.lastrowid
            for item in cat['items']:
                code = f"{shop_code}{str(item_counter).zfill(2)}"
                c.execute('INSERT INTO menu_item (category_id, name, price, note, code) VALUES (?, ?, ?, ?, ?)',
                          (category_id, item['name'], item['price'], item['note'], code))
                item_counter += 1
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    drink_shops = parse_drink()
    import_to_db(drink_shops)
    print('drink.md 已成功匯入資料庫！') 