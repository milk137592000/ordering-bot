from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, QuickReply, QuickReplyButton, MessageAction
import os
from dotenv import load_dotenv
from models import get_db
import datetime
from models import init_db
init_db()

load_dotenv()

app = Flask(__name__)

# 載入 LINE Bot 設定
CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# 範例：收到文字訊息時回覆
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text.strip()
    user_id = event.source.user_id
    display_name = None
    try:
        profile = line_bot_api.get_profile(user_id)
        display_name = profile.display_name
    except Exception:
        display_name = None
    reply = None
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().time()
    conn = get_db()
    c = conn.cursor()
    # --- 設定今日餐廳（需指定餐別）---
    if user_message.startswith("今日餐廳"):
        parts = user_message.split()
        if len(parts) >= 3:
            restaurant_name = parts[1]
            meal_type = parts[2]
            if meal_type not in ["中餐", "晚餐"]:
                reply = "餐別請輸入『中餐』或『晚餐』"
            else:
                c.execute('SELECT id FROM restaurant WHERE name=?', (restaurant_name,))
                r = c.fetchone()
                if not r:
                    reply = f"找不到餐廳：{restaurant_name}"
                else:
                    restaurant_id = r[0]
                    c.execute('INSERT OR REPLACE INTO today_restaurant (date, meal_type, restaurant_id) VALUES (?, ?, ?)', (today, meal_type, restaurant_id))
                    conn.commit()
                    reply = f"今日{meal_type}已設定為：{restaurant_name}"
        else:
            reply = "請輸入：今日餐廳 餐廳名稱 中餐/晚餐"
    # --- 點餐（自動判斷餐別與截止時間）---
    elif user_message.startswith("點餐"):
        # 判斷目前是哪一餐
        if now < datetime.time(9, 0):
            meal_type = "中餐"
            deadline = datetime.time(9, 0)
        elif now < datetime.time(17, 0):
            meal_type = "晚餐"
            deadline = datetime.time(17, 0)
        else:
            meal_type = None
        if not meal_type:
            reply = "目前已超過所有點餐截止時間。"
        else:
            # 檢查是否已截止
            if (meal_type == "中餐" and now >= datetime.time(9, 0)) or (meal_type == "晚餐" and now >= datetime.time(17, 0)):
                reply = f"{meal_type}點餐已截止。"
            else:
                parts = user_message.split()
                if len(parts) >= 3:
                    item_name = parts[1]
                    try:
                        quantity = int(parts[2])
                    except ValueError:
                        reply = "請輸入正確的數量（例如：點餐 招牌雞腿便當 2）"
                        conn.close()
                        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
                        return
                    # 取得今日餐廳
                    c.execute('SELECT restaurant_id FROM today_restaurant WHERE date=? AND meal_type=?', (today, meal_type))
                    r = c.fetchone()
                    if not r:
                        reply = f"請先設定今日{meal_type}餐廳。"
                    else:
                        restaurant_id = r[0]
                        # 找到品項
                        c.execute('''SELECT mi.id FROM menu_item mi
                                     JOIN menu_category mc ON mi.category_id = mc.id
                                     WHERE mi.name=? AND mc.restaurant_id=?''', (item_name, restaurant_id))
                        item = c.fetchone()
                        if not item:
                            reply = f"找不到品項：{item_name}"
                        else:
                            menu_item_id = item[0]
                            # 用戶註冊
                            c.execute('INSERT OR IGNORE INTO user (line_user_id, display_name) VALUES (?, ?)', (user_id, display_name))
                            c.execute('SELECT id FROM user WHERE line_user_id=?', (user_id,))
                            user_row = c.fetchone()
                            user_db_id = user_row[0]
                            # 寫入點餐紀錄
                            c.execute('''INSERT INTO order_record (user_id, date, meal_type, menu_item_id, quantity)
                                         VALUES (?, ?, ?, ?, ?)''', (user_db_id, today, meal_type, menu_item_id, quantity))
                            conn.commit()
                            reply = f"已為你登記：{item_name} x{quantity}（{meal_type}）"
                else:
                    reply = "請輸入：點餐 品項 數量（例如：點餐 招牌雞腿便當 2）"
    # --- 統計（可指定餐別）---
    elif user_message.startswith("統計"):
        parts = user_message.split()
        if len(parts) == 2 and parts[1] in ["中餐", "晚餐"]:
            meal_type = parts[1]
        else:
            # 預設自動判斷目前是哪一餐
            if now < datetime.time(9, 0):
                meal_type = "中餐"
            elif now < datetime.time(17, 0):
                meal_type = "晚餐"
            else:
                meal_type = "晚餐"  # 晚上查詢預設查晚餐
        c.execute('SELECT restaurant_id FROM today_restaurant WHERE date=? AND meal_type=?', (today, meal_type))
        r = c.fetchone()
        if not r:
            reply = f"今日{meal_type}尚未設定餐廳。"
        else:
            restaurant_id = r[0]
            c.execute('SELECT name FROM restaurant WHERE id=?', (restaurant_id,))
            restaurant_name = c.fetchone()[0]
            # 查詢所有點餐紀錄
            c.execute('''SELECT u.display_name, mi.name, orr.quantity, mi.price, (orr.quantity * mi.price) as total
                         FROM order_record orr
                         JOIN user u ON orr.user_id = u.id
                         JOIN menu_item mi ON orr.menu_item_id = mi.id
                         JOIN menu_category mc ON mi.category_id = mc.id
                         WHERE orr.date=? AND orr.meal_type=? AND mc.restaurant_id=?
                         ORDER BY u.display_name''', (today, meal_type, restaurant_id))
            rows = c.fetchall()
            if not rows:
                reply = f"今日{meal_type} {restaurant_name} 尚無點餐紀錄。"
            else:
                summary = {}
                total_sum = 0
                for row in rows:
                    name = row[0] or "(未知)"
                    item = row[1]
                    qty = row[2]
                    price = row[3]
                    subtotal = row[4]
                    total_sum += subtotal
                    if name not in summary:
                        summary[name] = []
                    summary[name].append(f"{item} x{qty} = ${subtotal}")
                lines = [f"今日{meal_type} {restaurant_name} 點餐統計："]
                for name, items in summary.items():
                    lines.append(f"{name}：")
                    lines.extend([f"  {i}" for i in items])
                lines.append(f"\n總金額：${total_sum}")
                reply = "\n".join(lines)
    # --- 查詢餐廳清單 ---
    elif user_message in ["餐廳", "查詢餐廳"]:
        c.execute('SELECT name FROM restaurant ORDER BY id')
        rows = c.fetchall()
        if rows:
            quick_reply_items = [
                QuickReplyButton(action=MessageAction(label=row[0], text=f"菜單 {row[0]}"))
                for row in rows
            ]
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="請選擇餐廳：",
                    quick_reply=QuickReply(items=quick_reply_items)
                )
            )
            conn.close()
            return
        else:
            reply = "目前沒有餐廳資料。"
    # --- 查詢餐廳菜單（分頁）---
    elif user_message.startswith("菜單"):
        import re
        parts = user_message.split()
        # 解析 page 參數
        page = 1
        page_match = re.search(r'page=(\d+)', user_message)
        if page_match:
            page = int(page_match.group(1))
            # 移除 page=... 參數
            parts = [p for p in parts if not p.startswith('page=')]
        PAGE_SIZE = 11
        if len(parts) == 3:
            # 「菜單 餐廳名稱 分類名稱」分頁顯示品項
            restaurant_name = parts[1]
            category_name = parts[2]
            c.execute('SELECT id FROM restaurant WHERE name=?', (restaurant_name,))
            r = c.fetchone()
            if not r:
                reply = f"找不到餐廳：{restaurant_name}"
            else:
                restaurant_id = r[0]
                c.execute('SELECT id FROM menu_category WHERE restaurant_id=? AND name=?', (restaurant_id, category_name))
                cat = c.fetchone()
                if not cat:
                    reply = f"找不到分類：{category_name}"
                else:
                    category_id = cat[0]
                    c.execute('SELECT name, price FROM menu_item WHERE category_id=?', (category_id,))
                    items = c.fetchall()
                    if not items:
                        reply = f"{restaurant_name}【{category_name}】尚無品項。"
                    else:
                        start = (page-1)*PAGE_SIZE
                        end = start+PAGE_SIZE
                        page_items = items[start:end]
                        quick_reply_items = [
                            QuickReplyButton(action=MessageAction(label=f"{item[0]} ${item[1]}", text=f"點餐 {item[0]} 1"))
                            for item in page_items
                        ]
                        # 加入下一頁按鈕
                        if end < len(items):
                            quick_reply_items.append(
                                QuickReplyButton(action=MessageAction(label="下一頁", text=f"菜單 {restaurant_name} {category_name} page={page+1}"))
                            )
                        line_bot_api.reply_message(
                            event.reply_token,
                            TextSendMessage(
                                text=f"請選擇 {restaurant_name}【{category_name}】的品項（第{page}頁）：",
                                quick_reply=QuickReply(items=quick_reply_items)
                            )
                        )
                        conn.close()
                        return
        elif len(parts) == 2:
            # 「菜單 餐廳名稱」分頁顯示分類
            restaurant_name = parts[1]
            c.execute('SELECT id FROM restaurant WHERE name=?', (restaurant_name,))
            r = c.fetchone()
            if not r:
                reply = f"找不到餐廳：{restaurant_name}"
            else:
                restaurant_id = r[0]
                c.execute('SELECT name FROM menu_category WHERE restaurant_id=?', (restaurant_id,))
                categories = c.fetchall()
                if not categories:
                    reply = f"{restaurant_name} 尚無菜單資料。"
                else:
                    start = (page-1)*PAGE_SIZE
                    end = start+PAGE_SIZE
                    page_cats = categories[start:end]
                    quick_reply_items = [
                        QuickReplyButton(action=MessageAction(label=cat[0], text=f"菜單 {restaurant_name} {cat[0]}"))
                        for cat in page_cats
                    ]
                    # 加入下一頁按鈕
                    if end < len(categories):
                        quick_reply_items.append(
                            QuickReplyButton(action=MessageAction(label="下一頁", text=f"菜單 {restaurant_name} page={page+1}"))
                        )
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(
                            text=f"請選擇 {restaurant_name} 的分類（第{page}頁）：",
                            quick_reply=QuickReply(items=quick_reply_items)
                        )
                    )
                    conn.close()
                    return
        else:
            reply = "請輸入：菜單 餐廳名稱"
    else:
        reply = f"你說了：{user_message}"
    conn.close()
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000) 