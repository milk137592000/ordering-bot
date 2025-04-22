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
            print(f"Restaurant: {current_restaurant}")
            restaurants.append({'name': current_restaurant, 'categories': []})
        elif line.startswith('## '):
            current_category = line.replace('## ', '').strip()
            print(f"  Category: {current_category}")
            if current_restaurant:
                restaurants[-1]['categories'].append({'name': current_category, 'items': []})
        elif line.startswith('- '):
            # 修正正則表達式，取得品項全名（到點號或價格之前）
            print(f"  Processing line: {line}")
            m = re.match(r'- (.+?)\s\.{2,}', line)
            # 更新價格匹配，匹配多個點號後面的數字
            price_match = re.search(r'\.{2,}\s*(\d+)', line)
            
            if m:
                print(f"    Matched: {m.group(1)}")
            else:
                print(f"    No match for item name")
                
            if price_match:
                print(f"    Price: ${price_match.group(1)}")
            else:
                print(f"    No match for price")
                
            if m and price_match and current_restaurant and current_category:
                item_name = m.group(1).strip()
                price = int(price_match.group(1))
                note = None
                print(f"    Added item: {item_name} - ${price}")
                restaurants[-1]['categories'][-1]['items'].append({'name': item_name, 'price': price, 'note': note})
            else:
                print(f"    Failed to add item")
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
        print(f"Added restaurant: {r['name']} (ID: {restaurant_id})")
        
        for cat in r['categories']:
            # 新增分類
            c.execute('INSERT INTO menu_category (restaurant_id, name) VALUES (?, ?)', (restaurant_id, cat['name']))
            category_id = c.lastrowid
            print(f"  Added category: {cat['name']} (ID: {category_id})")
            
            for item in cat['items']:
                # 新增品項
                c.execute('INSERT INTO menu_item (category_id, name, price, note) VALUES (?, ?, ?, ?)',
                          (category_id, item['name'], item['price'], item['note']))
                print(f"    Added item: {item['name']} - ${item['price']} (Category ID: {category_id})")
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    restaurants = parse_menu()
    import_to_db(restaurants)
    print('drink.md 已成功匯入資料庫！') 