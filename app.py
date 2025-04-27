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
    # --- 查詢餐廳菜單（一次顯示所有品項，含唯一編號）---
    elif user_message.startswith("菜單"):
        parts = user_message.split()
        if len(parts) == 2:
            restaurant_name = parts[1]
            c.execute('SELECT id FROM restaurant WHERE name=?', (restaurant_name,))
            r = c.fetchone()
            if not r:
                reply = f"找不到餐廳：{restaurant_name}"
            else:
                restaurant_id = r[0]
                # 取出所有分類及品項
                c.execute('''SELECT mc.name as category, mi.id, mi.name, mi.price FROM menu_category mc
                             JOIN menu_item mi ON mi.category_id = mc.id
                             WHERE mc.restaurant_id=? ORDER BY mc.id, mi.id''', (restaurant_id,))
                items = c.fetchall()
                if not items:
                    reply = f"{restaurant_name} 尚無菜單資料。"
                else:
                    lines = [f"{restaurant_name} 菜單："]
                    last_cat = None
                    for row in items:
                        cat, iid, iname, price = row
                        if cat != last_cat:
                            lines.append(f"\n【{cat}】")
                            last_cat = cat
                        lines.append(f"[{iid}] {iname} ${price}")
                    reply = "\n".join(lines)
        else:
            reply = "請輸入：菜單 餐廳名稱"
        conn.close()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return
    # --- 點餐新流程：輸入品項編號，回覆份數選單 ---
    # 用簡單 in-memory 狀態記錄 user_id -> menu_item_id
    if not hasattr(app, 'pending_order'):
        app.pending_order = {}

    if user_message.isdigit():
        menu_item_id = int(user_message)
        c.execute('SELECT mi.name, mi.price, mc.restaurant_id, r.name as restaurant_name FROM menu_item mi JOIN menu_category mc ON mi.category_id=mc.id JOIN restaurant r ON mc.restaurant_id=r.id WHERE mi.id=?', (menu_item_id,))
        item = c.fetchone()
        if not item:
            reply = f"找不到此品項編號：{menu_item_id}"
            conn.close()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return
        # 記錄這個 user_id 的 pending menu_item_id
        app.pending_order[user_id] = menu_item_id
        # 回覆份數 quick reply
        quick_reply_items = [QuickReplyButton(action=MessageAction(label=f"{i}份", text=str(i))) for i in range(1,6)]
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"你選擇了 [{menu_item_id}] {item['name']} (${item['price']})\n請選擇需要幾份：",
                quick_reply=QuickReply(items=quick_reply_items)
            )
        )
        conn.close()
        return

    # --- 點餐新流程：收到份數，完成點餐 ---
    if user_id in getattr(app, 'pending_order', {}):
        if user_message in [str(i) for i in range(1,6)]:
            menu_item_id = app.pending_order[user_id]
            c.execute('SELECT mi.name, mc.restaurant_id, r.name as restaurant_name FROM menu_item mi JOIN menu_category mc ON mi.category_id=mc.id JOIN restaurant r ON mc.restaurant_id=r.id WHERE mi.id=?', (menu_item_id,))
            item = c.fetchone()
            if not item:
                reply = "找不到此品項，請重新輸入編號。"
            else:
                # 判斷目前是哪一餐
                if now < datetime.time(9, 0):
                    meal_type = "中餐"
                elif now < datetime.time(17, 0):
                    meal_type = "晚餐"
                else:
                    meal_type = None
                if not meal_type:
                    reply = "目前已超過所有點餐截止時間。"
                else:
                    # 檢查今日餐廳
                    c.execute('SELECT restaurant_id FROM today_restaurant WHERE date=? AND meal_type=?', (today, meal_type))
                    r = c.fetchone()
                    if not r or r[0] != item['restaurant_id']:
                        reply = f"請先設定今日{meal_type}餐廳為 {item['restaurant_name']}。"
                    else:
                        # 用戶註冊
                        c.execute('INSERT OR IGNORE INTO user (line_user_id, display_name) VALUES (?, ?)', (user_id, display_name))
                        c.execute('SELECT id FROM user WHERE line_user_id=?', (user_id,))
                        user_row = c.fetchone()
                        user_db_id = user_row[0]
                        # 寫入點餐紀錄
                        c.execute('''INSERT INTO order_record (user_id, date, meal_type, menu_item_id, quantity)
                                     VALUES (?, ?, ?, ?, ?)''', (user_db_id, today, meal_type, menu_item_id, int(user_message)))
                        conn.commit()
                        reply = f"已為你登記：[{menu_item_id}] {item['name']} x{user_message}（{meal_type}）"
                # 清除 pending 狀態
                del app.pending_order[user_id]
            else:
                reply = "請選擇 1~5 份數，或重新輸入品項編號。"
            conn.close()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return
    else:
        reply = f"你說了：{user_message}"
    conn.close()
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000) 