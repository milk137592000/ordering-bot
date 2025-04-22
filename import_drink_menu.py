import re
import sqlite3
from models import get_db, init_db

MENU_FILE = 'drink.md'

def parse_menu():
    with open(MENU_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    restaurants = []
    current_restaurant = None
    current_category = None
    for line in lines:
        line = line.strip()
        if line.startswith('# ') and ('飲料店菜單' in line or ' 菜單' in line):
            current_restaurant = line.replace('# ', '').replace(' 飲料店菜單', '').replace(' 菜單', '').strip()
            restaurants.append({'name': current_restaurant, 'categories': []})
        elif line.startswith('## '):
            current_category = line.replace('## ', '').strip()
            if current_restaurant:
                restaurants[-1]['categories'].append({'name': current_category, 'items': []})
        elif line.startswith('- '):
            # 品項與價格
            m = re.match(r'- (.+?)\s*[.。．…]*\s*[MLL$]*(\$[0-9]+)(/\S+)?', line)
            if not m:
                m = re.match(r'- (.+?)\s*[.。．…]*\s*([MLL$]*[0-9]+)', line)
            if m and current_restaurant and current_category:
                item_name = m.group(1).strip()
                price = m.group(2).replace('$','').replace('M','').replace('L','')
                try:
                    price = int(price)
                except:
                    price = 0
                note = m.group(3).strip() if len(m.groups()) > 2 and m.group(3) else None
                restaurants[-1]['categories'][-1]['items'].append({'name': item_name, 'price': price, 'note': note})
    return restaurants

def import_to_db(restaurants):
    conn = get_db()
    c = conn.cursor()
    
    # 先清除所有飲料店資料
    c.execute('DELETE FROM menu_item WHERE category_id IN (SELECT id FROM menu_category WHERE restaurant_id IN (SELECT id FROM restaurant WHERE name IN ("鶴茶樓", "50嵐", "麻古飲料店", "水巷茶弄", "三分春色", "清原", "得正")))')
    c.execute('DELETE FROM menu_category WHERE restaurant_id IN (SELECT id FROM restaurant WHERE name IN ("鶴茶樓", "50嵐", "麻古飲料店", "水巷茶弄", "三分春色", "清原", "得正"))')
    c.execute('DELETE FROM restaurant WHERE name IN ("鶴茶樓", "50嵐", "麻古飲料店", "水巷茶弄", "三分春色", "清原", "得正")')
    
    for r in restaurants:
        # 新增餐廳
        c.execute('INSERT OR IGNORE INTO restaurant (name) VALUES (?)', (r['name'],))
        c.execute('SELECT id FROM restaurant WHERE name=?', (r['name'],))
        restaurant_id = c.fetchone()['id']
        for cat in r['categories']:
            # 新增分類
            c.execute('INSERT INTO menu_category (restaurant_id, name) VALUES (?, ?)', (restaurant_id, cat['name']))
            category_id = c.lastrowid
            for item in cat['items']:
                # 新增品項
                c.execute('INSERT INTO menu_item (category_id, name, price, note) VALUES (?, ?, ?, ?)',
                          (category_id, item['name'], item['price'], item['note']))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    restaurants = parse_menu()
    import_to_db(restaurants)
    print('drink.md 已成功匯入資料庫！') 