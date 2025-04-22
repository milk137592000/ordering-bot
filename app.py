from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, QuickReply, QuickReplyButton, MessageAction
import os
from dotenv import load_dotenv
from models import get_db
import datetime
from import_menu import import_to_db, parse_menu
from import_drink_menu import import_to_db as import_drink_to_db, parse_menu as parse_drink_menu

load_dotenv()

def safe_label(text, max_len=20):
    return text[:max_len-1] + '…' if len(text) > max_len else text

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

    # --- 吃啥：直接顯示今日餐廳菜單 ---
    if user_message.strip() == "吃啥":
        today = datetime.date.today().isoformat()
        # 先查晚餐
        c.execute('SELECT r.name FROM today_restaurant tr JOIN restaurant r ON tr.restaurant_id = r.id WHERE tr.date=? AND tr.meal_type=?', (today, "晚餐"))
        dinner_row = c.fetchone()
        # 再查中餐
        c.execute('SELECT r.name FROM today_restaurant tr JOIN restaurant r ON tr.restaurant_id = r.id WHERE tr.date=? AND tr.meal_type=?', (today, "中餐"))
        lunch_row = c.fetchone()
        if dinner_row:
            restaurant_name = dinner_row[0]
            meal_type = "晚餐"
        elif lunch_row:
            restaurant_name = lunch_row[0]
            meal_type = "中餐"
        else:
            reply = "今日尚未設定餐廳。"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            conn.close()
            return
        # 直接顯示菜單
        c.execute('SELECT name FROM menu_category WHERE restaurant_id=(SELECT id FROM restaurant WHERE name=?)', (restaurant_name,))
        categories = c.fetchall()
        if not categories:
            reply = f"{restaurant_name} 尚無菜單資料。"
        else:
            quick_reply_items = [
                QuickReplyButton(action=MessageAction(label=safe_label(cat[0]), text=f"菜單 {restaurant_name} {cat[0]}"))
                for cat in categories
            ]
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=f"請選擇 {restaurant_name} 的分類：",
                    quick_reply=QuickReply(items=quick_reply_items)
                )
            )
            conn.close()
            return

    # --- 喝啥：直接顯示今日飲料店菜單 ---
    elif user_message.strip() == "喝啥":
        today = datetime.date.today().isoformat()
        # 先查晚餐
        c.execute('SELECT r.name FROM today_drink td JOIN restaurant r ON td.restaurant_id = r.id WHERE td.date=? AND td.meal_type=?', (today, "晚餐"))
        dinner_row = c.fetchone()
        # 再查中餐
        c.execute('SELECT r.name FROM today_drink td JOIN restaurant r ON td.restaurant_id = r.id WHERE td.date=? AND td.meal_type=?', (today, "中餐"))
        lunch_row = c.fetchone()
        if dinner_row:
            restaurant_name = dinner_row[0]
            meal_type = "晚餐"
        elif lunch_row:
            restaurant_name = lunch_row[0]
            meal_type = "中餐"
        else:
            reply = "今日尚未設定飲料店。"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            conn.close()
            return
        # 直接顯示菜單
        c.execute('SELECT name FROM menu_category WHERE restaurant_id=(SELECT id FROM restaurant WHERE name=?)', (restaurant_name,))
        categories = c.fetchall()
        if not categories:
            reply = f"{restaurant_name} 尚無菜單資料。"
        else:
            quick_reply_items = [
                QuickReplyButton(action=MessageAction(label=safe_label(cat[0]), text=f"菜單 {restaurant_name} {cat[0]}"))
                for cat in categories
            ]
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=f"請選擇 {restaurant_name} 的分類：",
                    quick_reply=QuickReply(items=quick_reply_items)
                )
            )
            conn.close()
            return

    # --- 設定今日餐廳（需指定餐別）---
    elif user_message.startswith("今日餐廳") or user_message.startswith("吃"):
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
                    # 僅允許非飲料店
                    if is_drink_shop_name(restaurant_name):
                        reply = f"{restaurant_name} 是飲料店，請用『今日飲料』設定飲料店。"
                    else:
                        c.execute('INSERT OR REPLACE INTO today_restaurant (date, meal_type, restaurant_id) VALUES (?, ?, ?)', (today, meal_type, restaurant_id))
                        conn.commit()
                        reply = f"今日{meal_type}已設定為：{restaurant_name}"
        else:
            reply = "請輸入：今日餐廳 餐廳名稱 中餐/晚餐"

    # --- 設定今日飲料店（需指定餐別）---
    elif user_message.startswith("今日飲料"):
        parts = user_message.split()
        if len(parts) >= 3:
            drink_shop_name = parts[1]
            meal_type = parts[2]
            if meal_type not in ["中餐", "晚餐"]:
                reply = "餐別請輸入『中餐』或『晚餐』"
            else:
                c.execute('SELECT id FROM restaurant WHERE name=?', (drink_shop_name,))
                r = c.fetchone()
                if not r:
                    reply = f"找不到飲料店：{drink_shop_name}"
                else:
                    # 僅允許飲料店
                    if is_drink_shop_name(drink_shop_name):
                        restaurant_id = r[0]
                        c.execute('INSERT OR REPLACE INTO today_drink (date, meal_type, restaurant_id) VALUES (?, ?, ?)', (today, meal_type, restaurant_id))
                        conn.commit()
                        reply = f"今日{meal_type}已設定為飲料店：{drink_shop_name}"
                    else:
                        reply = f"{drink_shop_name} 不是飲料店，請用『今日餐廳』設定一般餐廳"
        else:
            reply = "請輸入：今日飲料 飲料店名稱 中餐/晚餐"

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
                # 查今日餐廳與飲料店
                c.execute('SELECT r.name, r.id FROM today_restaurant tr JOIN restaurant r ON tr.restaurant_id = r.id WHERE tr.date=? AND tr.meal_type=?', (today, meal_type))
                today_restaurant_row = c.fetchone()
                today_restaurant = today_restaurant_row[0] if today_restaurant_row else None
                today_restaurant_id = today_restaurant_row[1] if today_restaurant_row else None
                c.execute('SELECT r.name, r.id FROM today_drink td JOIN restaurant r ON td.restaurant_id = r.id WHERE td.date=? AND td.meal_type=?', (today, meal_type))
                today_drink_row = c.fetchone()
                today_drink = today_drink_row[0] if today_drink_row else None
                today_drink_id = today_drink_row[1] if today_drink_row else None
                # 只有「點餐 品項」時才需要自動判斷
                if len(parts) >= 2:
                    item_name = parts[1]
                    # 先查餐廳菜單
                    found_in_restaurant = False
                    found_in_drink = False
                    if today_restaurant_id:
                        c.execute('''SELECT mi.id FROM menu_item mi JOIN menu_category mc ON mi.category_id = mc.id WHERE mi.name=? AND mc.restaurant_id=?''', (item_name, today_restaurant_id))
                        found_in_restaurant = c.fetchone() is not None
                    if not found_in_restaurant and today_drink_id:
                        c.execute('''SELECT mi.id FROM menu_item mi JOIN menu_category mc ON mi.category_id = mc.id WHERE mi.name=? AND mc.restaurant_id=?''', (item_name, today_drink_id))
                        found_in_drink = c.fetchone() is not None
                    # 根據品項決定流程
                    if found_in_restaurant:
                        is_drink_shop = False
                        current_shop = today_restaurant
                        current_shop_id = today_restaurant_id
                    elif found_in_drink:
                        is_drink_shop = True
                        current_shop = today_drink
                        current_shop_id = today_drink_id
                    else:
                        reply = f"找不到品項：{item_name}"
                        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
                        conn.close()
                        return
                else:
                    # 沒有指定品項時，預設優先餐廳
                    if today_restaurant:
                        is_drink_shop = False
                        current_shop = today_restaurant
                        current_shop_id = today_restaurant_id
                    elif today_drink:
                        is_drink_shop = True
                        current_shop = today_drink
                        current_shop_id = today_drink_id
                    else:
                        reply = f"請先設定今日{meal_type}餐廳或飲料店。"
                        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
                        conn.close()
                        return
                # 飲料店互動流程
                if is_drink_shop:
                    # 1. 選品項，詢問甜度
                    if len(parts) == 2:
                        item_name = parts[1]
                        quick_reply_items = [
                            QuickReplyButton(action=MessageAction(label=f"{s}", text=f"點餐 {item_name} 甜度{s}")) for s in ["正常", "少糖", "半糖", "微糖", "無糖"]
                        ]
                        line_bot_api.reply_message(
                            event.reply_token,
                            TextSendMessage(
                                text="請選擇甜度",
                                quick_reply=QuickReply(items=quick_reply_items)
                            )
                        )
                        conn.close()
                        return
                    # 2. 選甜度，詢問冰塊
                    elif len(parts) == 3 and parts[2].startswith("甜度"):
                        item_name = parts[1]
                        sweetness = parts[2]
                        ice_options = ["正常", "少冰", "微冰", "去冰"]
                        quick_reply_items = [
                            QuickReplyButton(action=MessageAction(label=f"冰塊{opt}", text=f"點餐 {item_name} {sweetness} 冰塊{opt}")) for opt in ice_options
                        ]
                        line_bot_api.reply_message(
                            event.reply_token,
                            TextSendMessage(
                                text="請選擇冰塊（正常/少冰/微冰/去冰）",
                                quick_reply=QuickReply(items=quick_reply_items)
                            )
                        )
                        conn.close()
                        return
                    # 3. 選冰塊，詢問杯數
                    elif len(parts) == 4 and parts[2].startswith("甜度") and parts[3].startswith("冰塊"):
                        item_name = parts[1]
                        sweetness = parts[2]
                        ice = parts[3]
                        quick_reply_items = [
                            QuickReplyButton(action=MessageAction(label=f"{i}杯", text=f"點餐 {item_name} {sweetness} {ice} {i}")) for i in range(1, 6)
                        ]
                        line_bot_api.reply_message(
                            event.reply_token,
                            TextSendMessage(
                                text="請選擇杯數（1~5）",
                                quick_reply=QuickReply(items=quick_reply_items)
                            )
                        )
                        conn.close()
                        return
                    # 4. 完成飲料點餐
                    elif len(parts) == 5 and parts[2].startswith("甜度") and parts[3].startswith("冰塊"):
                        item_name = parts[1]
                        sweetness = parts[2]
                        ice = parts[3]
                        try:
                            quantity = int(parts[4])
                        except ValueError:
                            reply = "請輸入正確的杯數（例如：點餐 紅茶 甜度正常 冰塊正常 2）"
                            conn.close()
                            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
                            return
                        # 取得今日飲料店
                        c.execute('SELECT restaurant_id FROM today_drink WHERE date=? AND meal_type=?', (today, meal_type))
                        r = c.fetchone()
                        if not r:
                            reply = f"請先設定今日{meal_type}飲料店。"
                        else:
                            restaurant_id = r[0]
                            # 找到品項
                            c.execute('''SELECT mi.id FROM menu_item mi\n                                         JOIN menu_category mc ON mi.category_id = mc.id\n                                         WHERE mi.name=? AND mc.restaurant_id=?''', (item_name, restaurant_id))
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
                                # 寫入點餐紀錄（甜度冰塊資訊可加在 note 或 reply）
                                c.execute('''INSERT INTO order_record (user_id, date, meal_type, menu_item_id, quantity)\n                                             VALUES (?, ?, ?, ?, ?)''', (user_db_id, today, meal_type, menu_item_id, quantity))
                                conn.commit()
                                reply = f"已為你登記：{item_name} x{quantity}（{meal_type}）\n{sweetness}、{ice}"
                        # 完成
                    else:
                        reply = "請依序選擇品項、甜度、冰塊、杯數。"
                # 一般餐廳互動流程
                else:
                    # 1. 選品項，詢問份數
                    if len(parts) == 2:
                        item_name = parts[1]
                        quick_reply_items = [
                            QuickReplyButton(action=MessageAction(label=f"{i}份", text=f"點餐 {item_name} {i}")) for i in range(1, 6)
                        ]
                        line_bot_api.reply_message(
                            event.reply_token,
                            TextSendMessage(
                                text="請選擇份數（1~5）",
                                quick_reply=QuickReply(items=quick_reply_items)
                            )
                        )
                        conn.close()
                        return
                    # 2. 完成點餐
                    elif len(parts) == 3:
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
                            c.execute('''SELECT mi.id FROM menu_item mi\n                                         JOIN menu_category mc ON mi.category_id = mc.id\n                                         WHERE mi.name=? AND mc.restaurant_id=?''', (item_name, restaurant_id))
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
                                c.execute('''INSERT INTO order_record (user_id, date, meal_type, menu_item_id, quantity)\n                                             VALUES (?, ?, ?, ?, ?)''', (user_db_id, today, meal_type, menu_item_id, quantity))
                                conn.commit()
                                reply = f"已為你登記：{item_name} x{quantity}（{meal_type}）"
                    else:
                        reply = "請輸入：點餐 品項 數量（例如：點餐 招牌雞腿便當 2）"

    # --- 今日午餐/晚餐統計 ---
    elif user_message.strip() in ["今日午餐統計", "今日晚餐統計"]:
        meal_type = "中餐" if "午餐" in user_message else "晚餐"
        today = datetime.date.today().isoformat()
        # 查詢所有今日餐廳與飲料店
        c.execute('SELECT id, name FROM restaurant')
        all_restaurants = c.fetchall()
        food_ids = []
        drink_ids = []
        for rid, name in all_restaurants:
            if is_drink_shop_name(name):
                drink_ids.append(rid)
            else:
                food_ids.append(rid)
        lines = []
        total_sum = 0
        # 餐點
        lines.append("【餐點】")
        found_food = False
        for rid in food_ids:
            c.execute('''SELECT u.display_name, mi.name, orr.quantity, mi.price, (orr.quantity * mi.price) as total\n                         FROM order_record orr\n                         JOIN user u ON orr.user_id = u.id\n                         JOIN menu_item mi ON orr.menu_item_id = mi.id\n                         JOIN menu_category mc ON mi.category_id = mc.id\n                         WHERE orr.date=? AND orr.meal_type=? AND mc.restaurant_id=?\n                         ORDER BY u.display_name''', (today, meal_type, rid))
            rows = c.fetchall()
            if not rows:
                continue
            found_food = True
            summary = {}
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
            for name, items in summary.items():
                lines.append(f"{name}：")
                lines.extend([f"  {i}" for i in items])
        if not found_food:
            lines.append("(無餐點紀錄)")
        # 飲料
        lines.append("\n【飲料】")
        found_drink = False
        for rid in drink_ids:
            c.execute('''SELECT u.display_name, mi.name, orr.quantity, mi.price, (orr.quantity * mi.price) as total\n                         FROM order_record orr\n                         JOIN user u ON orr.user_id = u.id\n                         JOIN menu_item mi ON orr.menu_item_id = mi.id\n                         JOIN menu_category mc ON mi.category_id = mc.id\n                         WHERE orr.date=? AND orr.meal_type=? AND mc.restaurant_id=?\n                         ORDER BY u.display_name''', (today, meal_type, rid))
            rows = c.fetchall()
            if not rows:
                continue
            found_drink = True
            summary = {}
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
            for name, items in summary.items():
                lines.append(f"{name}：")
                lines.extend([f"  {i}" for i in items])
        lines.append(f"\n總金額：${total_sum}")
        reply = "\n".join(lines)

    # --- 餐點/飲料 統計 ---
    elif user_message.strip() in ["餐點 統計", "飲料 統計"]:
        is_drink = user_message.strip().startswith("飲料")
        # 預設自動判斷目前是哪一餐
        if now < datetime.time(9, 0):
            meal_type = "中餐"
        elif now < datetime.time(17, 0):
            meal_type = "晚餐"
        else:
            meal_type = "晚餐"
        # 查詢今日所有設定的餐廳/飲料店
        c.execute('SELECT restaurant_id FROM today_restaurant WHERE date=? AND meal_type=?', (today, meal_type))
        restaurant_ids = [row[0] for row in c.fetchall()]
        if not restaurant_ids:
            reply = f"今日{meal_type}尚未設定餐廳。"
        else:
            lines = [f"今日{meal_type} {'飲料' if is_drink else '餐點'}統計："]
            total_sum = 0
            found_any = False
            for rid in restaurant_ids:
                c.execute('SELECT name FROM restaurant WHERE id=?', (rid,))
                restaurant_name = c.fetchone()[0]
                is_this_drink = is_drink_shop_name(restaurant_name)
                if is_drink != is_this_drink:
                    continue
                # 查詢該餐廳/飲料店所有點餐紀錄
                c.execute('''SELECT u.display_name, mi.name, orr.quantity, mi.price, (orr.quantity * mi.price) as total
                             FROM order_record orr
                             JOIN user u ON orr.user_id = u.id
                             JOIN menu_item mi ON orr.menu_item_id = mi.id
                             JOIN menu_category mc ON mi.category_id = mc.id
                             WHERE orr.date=? AND orr.meal_type=? AND mc.restaurant_id=?
                             ORDER BY u.display_name''', (today, meal_type, rid))
                rows = c.fetchall()
                if not rows:
                    continue
                found_any = True
                lines.append(f"\n【{restaurant_name}】")
                summary = {}
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
                for name, items in summary.items():
                    lines.append(f"{name}：")
                    lines.extend([f"  {i}" for i in items])
            if found_any:
                lines.append(f"\n總金額：${total_sum}")
                reply = "\n".join(lines)
            else:
                reply = f"今日{meal_type} {'飲料' if is_drink else '餐點'}尚無點餐紀錄。"

    # --- 查詢餐廳清單（分頁，僅餐廳） ---
    elif user_message.startswith("餐廳") or user_message in ["餐廳", "查詢餐廳"]:
        import re
        page = 1
        page_match = re.search(r'page=(\d+)', user_message)
        if page_match:
            page = int(page_match.group(1))
        PAGE_SIZE = 12
        # 只顯示非飲料店
        c.execute("SELECT name FROM restaurant WHERE name NOT LIKE '%飲料%' AND name NOT LIKE '%茶%' AND name NOT LIKE '%春色%' AND name NOT LIKE '%清原%' AND name NOT LIKE '%得正%' AND name NOT LIKE '%麻古%' AND name NOT LIKE '%50嵐%' AND name NOT LIKE '%鶴茶樓%' AND name NOT LIKE '%水巷茶弄%' ORDER BY id")
        rows = c.fetchall()
        if rows:
            start = (page-1)*PAGE_SIZE
            end = start+PAGE_SIZE
            page_rows = rows[start:end]
            quick_reply_items = [
                QuickReplyButton(action=MessageAction(label=safe_label(row[0]), text=f"菜單 {row[0]}"))
                for row in page_rows
            ]
            if end < len(rows):
                quick_reply_items.append(
                    QuickReplyButton(action=MessageAction(label=safe_label("下一頁"), text=f"餐廳 page={page+1}"))
                )
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=f"請選擇餐廳（第{page}頁）：",
                    quick_reply=QuickReply(items=quick_reply_items)
                )
            )
            conn.close()
            return
        else:
            reply = "目前沒有餐廳資料。"

    # --- 查詢餐廳菜單（分頁） ---
    elif user_message.startswith("菜單"):
        import re
        parts = user_message.split()
        page = 1
        page_match = re.search(r'page=(\d+)', user_message)
        if page_match:
            page = int(page_match.group(1))
            parts = [p for p in parts if not p.startswith('page=')]
        PAGE_SIZE = 12
        if len(parts) == 3:
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
                        is_drink_shop = is_drink_shop_name(restaurant_name)
                        page_items = items[start:end]
                        quick_reply_items = [
                            QuickReplyButton(
                                action=MessageAction(
                                    label=safe_label(f"{item[0]} ${item[1]}"),
                                    text=f"點餐 {item[0]}" if is_drink_shop else f"點餐 {item[0]}"
                                )
                            )
                            for item in page_items
                        ]
                        if end < len(items):
                            quick_reply_items.append(
                                QuickReplyButton(action=MessageAction(label=safe_label("下一頁"), text=f"菜單 {restaurant_name} {category_name} page={page+1}"))
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
                        QuickReplyButton(action=MessageAction(label=safe_label(cat[0]), text=f"菜單 {restaurant_name} {cat[0]}"))
                        for cat in page_cats
                    ]
                    if end < len(categories):
                        quick_reply_items.append(
                            QuickReplyButton(action=MessageAction(label=safe_label("下一頁"), text=f"菜單 {restaurant_name} page={page+1}"))
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

    # --- 隨機選擇今日餐廳 ---
    elif user_message.startswith("隨便吃"):
        parts = user_message.split()
        if len(parts) == 2 and parts[1] in ["中餐", "午餐", "晚餐"]:
            meal_type = parts[1]
            if meal_type == "午餐":
                meal_type = "中餐"
            # 只選非飲料店
            c.execute("SELECT id, name FROM restaurant WHERE name NOT LIKE '%飲料%' AND name NOT LIKE '%茶%' AND name NOT LIKE '%春色%' AND name NOT LIKE '%清原%' AND name NOT LIKE '%得正%' AND name NOT LIKE '%麻古%' AND name NOT LIKE '%50嵐%' AND name NOT LIKE '%鶴茶樓%' AND name NOT LIKE '%水巷茶弄%' ORDER BY RANDOM() LIMIT 1")
            r = c.fetchone()
            if not r:
                reply = "目前沒有餐廳資料。"
            else:
                restaurant_id, restaurant_name = r
                today = datetime.date.today().isoformat()
                c.execute('INSERT OR REPLACE INTO today_restaurant (date, meal_type, restaurant_id) VALUES (?, ?, ?)', (today, meal_type, restaurant_id))
                conn.commit()
                reply = f"今日{meal_type}已隨機選擇：{restaurant_name}"
        else:
            reply = "請輸入：隨便吃 午餐/晚餐"

    # --- 隨機選擇今日飲料店 ---
    elif user_message.startswith("隨便喝"):
        parts = user_message.split()
        if len(parts) == 2 and parts[1] in ["中餐", "午餐", "晚餐"]:
            meal_type = parts[1]
            if meal_type == "午餐":
                meal_type = "中餐"
            # 只選飲料店
            c.execute("SELECT id, name FROM restaurant WHERE name LIKE '%飲料%' OR name LIKE '%茶%' OR name LIKE '%春色%' OR name LIKE '%清原%' OR name LIKE '%得正%' OR name LIKE '%麻古%' OR name LIKE '%50嵐%' OR name LIKE '%鶴茶樓%' OR name LIKE '%水巷茶弄%' ORDER BY RANDOM() LIMIT 1")
            r = c.fetchone()
            if not r:
                reply = "目前沒有飲料店資料。"
            else:
                restaurant_id, restaurant_name = r
                today = datetime.date.today().isoformat()
                c.execute('INSERT OR REPLACE INTO today_drink (date, meal_type, restaurant_id) VALUES (?, ?, ?)', (today, meal_type, restaurant_id))
                conn.commit()
                reply = f"今日{meal_type}已隨機選擇飲料店：{restaurant_name}"
        else:
            reply = "請輸入：隨便喝 午餐/晚餐"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        conn.close()
        return

    # --- 飲料店下拉式選單（分頁） ---
    elif user_message.startswith("飲料") or user_message == "飲料":
        import re
        page = 1
        page_match = re.search(r'page=(\d+)', user_message)
        if page_match:
            page = int(page_match.group(1))
        PAGE_SIZE = 12
        # 只顯示飲料店
        c.execute("SELECT name FROM restaurant WHERE name LIKE '%飲料%' OR name LIKE '%茶%' OR name LIKE '%春色%' OR name LIKE '%清原%' OR name LIKE '%得正%' OR name LIKE '%麻古%' OR name LIKE '%50嵐%' OR name LIKE '%鶴茶樓%' OR name LIKE '%水巷茶弄%' ORDER BY id")
        rows = c.fetchall()
        if rows:
            start = (page-1)*PAGE_SIZE
            end = start+PAGE_SIZE
            page_rows = rows[start:end]
            quick_reply_items = [
                QuickReplyButton(action=MessageAction(label=safe_label(row[0]), text=f"菜單 {row[0]}"))
                for row in page_rows
            ]
            if end < len(rows):
                quick_reply_items.append(
                    QuickReplyButton(action=MessageAction(label=safe_label("下一頁"), text=f"飲料 page={page+1}"))
                )
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=f"請選擇飲料店（第{page}頁）：",
                    quick_reply=QuickReply(items=quick_reply_items)
                )
            )
            conn.close()
            return
        else:
            reply = "目前沒有飲料店資料。"

    # --- 今日消費明細 ---
    elif user_message.strip() == "今日消費明細":
        today = datetime.date.today().isoformat()
        # 判斷目前是哪一餐
        if now < datetime.time(9, 0):
            meal_type = "中餐"
        elif now < datetime.time(17, 0):
            meal_type = "晚餐"
        else:
            meal_type = "晚餐"
        # 查詢所有點餐紀錄（餐點+飲料）
        c.execute('''SELECT u.display_name, SUM(orr.quantity * mi.price) as total
                     FROM order_record orr
                     JOIN user u ON orr.user_id = u.id
                     JOIN menu_item mi ON orr.menu_item_id = mi.id
                     JOIN menu_category mc ON mi.category_id = mc.id
                     WHERE orr.date=? AND orr.meal_type=?
                     GROUP BY u.display_name''', (today, meal_type))
        rows = c.fetchall()
        lines = [f"今日{meal_type}消費明細："]
        total_sum = 0
        if rows:
            for row in rows:
                name = row[0] or "(未知)"
                subtotal = row[1]
                total_sum += subtotal
                lines.append(f"{name}：${subtotal}")
            lines.append(f"總金額：${total_sum}")
        else:
            lines.append("今日尚無點餐紀錄。")
        reply = "\n".join(lines)

    else: # 所有其他指令都落到這裡
        reply = f"無法識別指令：{user_message}"

    conn.close() # 確保所有路徑都會關閉連線
    if reply: # 只有需要文字回覆時才呼叫 reply_message
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply)
        )

def is_db_empty(db_path):
    import sqlite3
    if not os.path.exists(db_path):
        return True
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    try:
        c.execute('SELECT COUNT(*) FROM restaurant')
        count = c.fetchone()[0]
        conn.close()
        return count == 0
    except Exception:
        conn.close()
        return True

# 啟動時自動匯入 menu.md 和 drink.md
if is_db_empty('db2.sqlite3'):
    print('資料庫為空，清空資料表...')
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM menu_item')
    c.execute('DELETE FROM menu_category')
    c.execute('DELETE FROM restaurant')
    conn.commit()
    conn.close()
    
    print('自動匯入 menu.md ...')
    import_to_db(parse_menu())
    print('menu.md 已自動匯入資料庫！')
    print('自動匯入 drink.md ...')
    import_drink_to_db(parse_drink_menu())
    print('drink.md 已自動匯入資料庫！')

# 新增：飲料店判斷 function
def is_drink_shop_name(name):
    drink_shops = ["飲料", "茶", "春色", "清原", "得正", "麻古", "50嵐", "鶴茶樓", "水巷茶弄"]
    return any(x in name for x in drink_shops)

if __name__ == "__main__":
    import_to_db(parse_menu())
    import_drink_to_db(parse_drink_menu())
    app.run(host='0.0.0.0', port=5000) 