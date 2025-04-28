import re
import sqlite3
from models import get_db, init_db

MENU_FILE = 'menu.md'
DRINK_FILE = 'drink.md'

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
            m = re.match(r'- (.+?)\s*[.。．…]*\s*\$([0-9]+)(/\S+)?', line)
            if m and current_restaurant and current_category:
                item_name = m.group(1).strip()
                price = int(m.group(2))
                note = m.group(3).strip() if m.group(3) else None
                restaurants[-1]['categories'][-1]['items'].append({'name': item_name, 'price': price, 'note': note})
    return restaurants

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
            m = re.match(r'- (.+?)\s*[.。．…]*\s*([0-9]+)(/\S+)?', line)
            if m and current_shop and current_category:
                item_name = m.group(1).strip()
                price = int(m.group(2))
                note = m.group(3).strip() if m.group(3) else None
                drink_shops[-1]['categories'][-1]['items'].append({'name': item_name, 'price': price, 'note': note})
    return drink_shops

def gen_alpha2(n):
    return chr(65 + n // 26) + chr(65 + n % 26)

def clear_tables():
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM order_record')
    c.execute('DELETE FROM today_restaurant')
    c.execute('DELETE FROM user')
    c.execute('DELETE FROM menu_item')
    c.execute('DELETE FROM menu_category')
    c.execute('DELETE FROM restaurant')
    conn.commit()
    conn.close()

def import_all():
    init_db()
    clear_tables()
    menu_restaurants = parse_menu()
    drink_shops = parse_drink()
    # 插入餐廳
    conn = get_db()
    c = conn.cursor()
    for shop in menu_restaurants:
        c.execute('INSERT INTO restaurant (name, type) VALUES (?, ?)', (shop['name'], '餐廳'))
    for shop in drink_shops:
        c.execute('INSERT INTO restaurant (name, type) VALUES (?, ?)', (shop['name'], '飲料店'))
    conn.commit()
    # 分配雙字母 code
    c.execute('SELECT id FROM restaurant ORDER BY id')
    ids = [row['id'] for row in c.fetchall()]
    for idx, rid in enumerate(ids):
        code = gen_alpha2(idx)
        c.execute('UPDATE restaurant SET code=? WHERE id=?', (code, rid))
    conn.commit()
    # 重新查一次 name->(id,code)
    c.execute('SELECT id, name, code FROM restaurant')
    shop_map = {row['name']: (row['id'], row['code']) for row in c.fetchall()}
    # 插入所有品項
    for shop in menu_restaurants:
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
    import_all()
    print('menu.md + drink.md 已成功合併匯入資料庫，所有 code 已正確分配！') 