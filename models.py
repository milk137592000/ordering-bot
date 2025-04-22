import sqlite3

DB_NAME = 'db2.sqlite3'

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    # 餐廳表
    c.execute('''
        CREATE TABLE IF NOT EXISTS restaurant (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    ''')
    # 菜單分類表
    c.execute('''
        CREATE TABLE IF NOT EXISTS menu_category (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            FOREIGN KEY (restaurant_id) REFERENCES restaurant(id)
        )
    ''')
    # 菜單品項表
    c.execute('''
        CREATE TABLE IF NOT EXISTS menu_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            note TEXT,
            FOREIGN KEY (category_id) REFERENCES menu_category(id)
        )
    ''')
    # 用戶表
    c.execute('''
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            line_user_id TEXT NOT NULL UNIQUE,
            display_name TEXT
        )
    ''')
    # 今日餐廳表
    c.execute('''
        CREATE TABLE IF NOT EXISTS today_restaurant (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            meal_type TEXT NOT NULL, -- '中餐' 或 '晚餐'
            restaurant_id INTEGER NOT NULL,
            UNIQUE(date, meal_type),
            FOREIGN KEY (restaurant_id) REFERENCES restaurant(id)
        )
    ''')
    # 今日飲料店表
    c.execute('''
        CREATE TABLE IF NOT EXISTS today_drink (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            meal_type TEXT NOT NULL, -- '中餐' 或 '晚餐'
            restaurant_id INTEGER NOT NULL,
            UNIQUE(date, meal_type),
            FOREIGN KEY (restaurant_id) REFERENCES restaurant(id)
        )
    ''')
    # 點餐紀錄表
    c.execute('''
        CREATE TABLE IF NOT EXISTS order_record (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            meal_type TEXT NOT NULL, -- '中餐' 或 '晚餐'
            menu_item_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES user(id),
            FOREIGN KEY (menu_item_id) REFERENCES menu_item(id)
        )
    ''')
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print('資料庫初始化完成') 