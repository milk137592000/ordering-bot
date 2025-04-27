import re
import sqlite3
from models import get_db, init_db

MENU_FILE = 'menu.md'

def parse_menu():
    with open(MENU_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    restaurants = []
    current_restaurant = None
    current_category = None
    for line in lines:
        line = line.strip()
        if line.startswith('# ') and '餐廳菜單' in line:
            current_restaurant = line.replace('# ', '').replace(' 餐廳菜單', '').strip()
            restaurants.append({'name': current_restaurant, 'categories': []})
        elif line.startswith('## '):
            current_category = line.replace('## ', '').strip()
            if current_restaurant:
                restaurants[-1]['categories'].append({'name': current_category, 'items': []})
        elif line.startswith('- '):
            # 品項與價格
            m = re.match(r'- (.+?)\s*[.。．…]*\s*\$([0-9]+)(/\S+)?', line)
            if m and current_restaurant and current_category:
                item_name = m.group(1).strip()
                price = int(m.group(2))
                note = m.group(3).strip() if m.group(3) else None
                restaurants[-1]['categories'][-1]['items'].append({'name': item_name, 'price': price, 'note': note})
    return restaurants

def get_restaurant_prefix(name):
    # 取餐廳拼音首字母，特殊例外可自行擴充
    mapping = {
        '吃什麼': 'C',
        '進膳': 'J',
        '佳味燒肉飯': 'G',
        '高林木片便當': 'K',
        '小品牛排': 'X',
        '八廚': 'B',
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

def import_to_db(restaurants):
    conn = get_db()
    c = conn.cursor()
    # 先插入所有餐廳
    for r in restaurants:
        c.execute('INSERT OR IGNORE INTO restaurant (name) VALUES (?)', (r['name'],))
    conn.commit()
    assign_restaurant_codes()
    # 重新查一次 name->(id,code)
    c.execute('SELECT id, name, code FROM restaurant')
    rest_map = {row['name']: (row['id'], row['code']) for row in c.fetchall()}
    for r in restaurants:
        restaurant_id, rest_code = rest_map[r['name']]
        item_counter = 1
        for cat in r['categories']:
            c.execute('INSERT INTO menu_category (restaurant_id, name) VALUES (?, ?)', (restaurant_id, cat['name']))
            category_id = c.lastrowid
            for item in cat['items']:
                code = f"{rest_code}{str(item_counter).zfill(2)}"
                c.execute('INSERT INTO menu_item (category_id, name, price, note, code) VALUES (?, ?, ?, ?, ?)',
                          (category_id, item['name'], item['price'], item['note'], code))
                item_counter += 1
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    restaurants = parse_menu()
    import_to_db(restaurants)
    print('menu.md 已成功匯入資料庫！') 