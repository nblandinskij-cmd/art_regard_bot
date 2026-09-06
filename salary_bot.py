#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import logging
import sys
from datetime import datetime
from telegram import Update, WebAppInfo, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ---------- Настройка логирования ----------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ---------- Переменные окружения ----------
TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # Например: https://ваш-домен.ru/webhook
PORT = int(os.environ.get("PORT", 8443))

# Пароль для получения прав администратора
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

# ---------- Инициализация данных (для простоты используем словарь в памяти) ----------
# В реальном проекте используйте базу данных или файлы.
data = {
    "masters": [],          # список мастеров [{"name": "Иван", "branch": "Основной"}]
    "incomes": [],          # подтверждённые доходы
    "users": {},            # user_id -> master_name
    "branches": ["Основной"],
    "pending": [],          # заявки на подтверждение
    "payments": [],         # выплаты
    "settings": {"deduction_percent": 70.0}
}

# ---------- Вспомогательные функции ----------
def save_data():
    # Для демонстрации сохраняем в файлы (можно заменить на БД)
    with open("data.json", "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_data():
    global data
    try:
        with open("data.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        save_data()

load_data()

def is_admin(user_id):
    # Получаем список админов из переменной окружения или из файла
    admin_ids = os.environ.get("ADMIN_IDS", "")
    if admin_ids:
        return str(user_id) in admin_ids.split(",")
    return False

def get_balance(master_name):
    total_income = sum(inc["amount"] for inc in data["incomes"] if inc.get("master") == master_name)
    total_payments = sum(pay["amount"] for pay in data["payments"] if pay.get("master") == master_name)
    return total_income - total_payments

# ---------- Обработчики команд ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_admin(user_id):
        role = "admin"
    elif str(user_id) in data["users"]:
        role = "master"
    else:
        role = "unregistered"
    # Отправляем приветствие и предлагаем открыть мини-приложение
    web_app_url = os.environ.get("WEB_APP_URL", "https://ваш-домен.ru")
    keyboard = [
        [KeyboardButton("🌐 Открыть приложение", web_app=WebAppInfo(url=web_app_url))]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    text = "🌟 Добро пожаловать в ArtRegardFinance!\n\n"
    if role == "admin":
        text += "Вы вошли как администратор."
    elif role == "master":
        text += f"Вы вошли как мастер {data['users'][str(user_id)]}."
    else:
        text += "Вы не зарегистрированы. Нажмите 'Открыть приложение' для активации."
    text += "\n\nИспользуйте кнопку ниже для открытия мини-приложения."
    await update.message.reply_text(text, reply_markup=reply_markup)

async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка данных из мини-приложения."""
    user_id = update.effective_user.id
    try:
        payload = json.loads(update.effective_message.web_app_data.data)
        action = payload.get("action")
        response = {"action": action}

        if action == "get_role":
            if is_admin(user_id):
                role = "admin"
                master_name = None
            elif str(user_id) in data["users"]:
                role = "master"
                master_name = data["users"][str(user_id)]
            else:
                role = "unregistered"
                master_name = None
            response.update({"role": role, "masterName": master_name})

        elif action == "activate":
            name = payload.get("name")
            if name in data["users"].values():
                response["success"] = False
                response["message"] = "Имя уже занято другим пользователем."
            else:
                data["users"][str(user_id)] = name
                save_data()
                response["success"] = True
                response["message"] = f"Вы активированы как мастер '{name}'."
                response["masterName"] = name

        elif action == "add_income":
            if not is_admin(user_id) and str(user_id) not in data["users"]:
                response["message"] = "Вы не зарегистрированы."
                await update.message.reply_text(json.dumps(response))
                return
            master_name = data["users"].get(str(user_id))
            if not master_name and not is_admin(user_id):
                response["message"] = "Ошибка: мастер не найден."
                await update.message.reply_text(json.dumps(response))
                return
            text = payload.get("text")
            # Парсинг чисел (упрощённый)
            import re
            nums = re.findall(r'\d+(?:\.\d+)?', text)
            total = sum(float(n) for n in nums)
            if total == 0:
                response["message"] = "Не найдено чисел."
                await update.message.reply_text(json.dumps(response))
                return
            percent = data["settings"].get("deduction_percent", 70)
            deduction = total * (percent / 100)
            net = total - deduction
            # Создаём заявку
            pending_item = {
                "master": master_name,
                "original_amount": total,
                "amount": net,
                "text": text,
                "date": datetime.now().isoformat(),
                "status": "pending"
            }
            data["pending"].append(pending_item)
            save_data()
            response.update({
                "accrued": round(total, 2),
                "deductions": round(deduction, 2),
                "net": round(net, 2),
                "percent": percent,
                "message": "Заявка отправлена на подтверждение."
            })
            # Уведомить админов
            admin_ids = os.environ.get("ADMIN_IDS", "").split(",")
            for admin_id in admin_ids:
                if admin_id:
                    try:
                        await context.bot.send_message(
                            admin_id,
                            f"📨 Новая заявка от {master_name}\nСумма: {net:.2f} руб.\nТекст: {text[:100]}..."
                        )
                    except:
                        pass

        elif action == "get_my_stats":
            master_name = data["users"].get(str(user_id))
            if not master_name:
                response["message"] = "Вы не зарегистрированы."
            else:
                filtered = [inc for inc in data["incomes"] if inc.get("master") == master_name]
                total = sum(inc["amount"] for inc in filtered)
                count = len(filtered)
                avg = total / count if count else 0
                response.update({"total": round(total, 2), "count": count, "avg": round(avg, 2)})

        elif action == "get_my_balance":
            master_name = data["users"].get(str(user_id))
            if not master_name:
                response["message"] = "Вы не зарегистрированы."
            else:
                bal = get_balance(master_name)
                response["balance"] = round(bal, 2)

        elif action == "get_masters":
            if not is_admin(user_id):
                response["message"] = "Только для администратора."
            else:
                response["masters"] = data["masters"]

        elif action == "get_branches":
            response["branches"] = data["branches"]

        elif action == "add_branch":
            if not is_admin(user_id):
                response["message"] = "Только для администратора."
            else:
                name = payload.get("name")
                if name and name not in data["branches"]:
                    data["branches"].append(name)
                    save_data()
                    response["branches"] = data["branches"]
                    response["message"] = f"Филиал '{name}' добавлен."
                else:
                    response["message"] = "Филиал уже существует или имя пустое."

        elif action == "get_stats":
            if not is_admin(user_id):
                response["message"] = "Только для администратора."
            else:
                branch = payload.get("branch")
                period = payload.get("period")
                # Фильтр по периоду (упрощённо)
                filtered = data["incomes"]
                if branch:
                    filtered = [inc for inc in filtered if inc.get("branch") == branch]
                # Для простоты игнорируем период в демо
                total = sum(inc["amount"] for inc in filtered)
                count = len(filtered)
                avg = total / count if count else 0
                # Топ мастеров
                masters_sum = {}
                for inc in filtered:
                    m = inc.get("master", "Неизвестно")
                    masters_sum[m] = masters_sum.get(m, 0) + inc["amount"]
                top = sorted(masters_sum.items(), key=lambda x: x[1], reverse=True)[:5]
                top_list = [{"name": m, "amount": round(s, 2)} for m, s in top]
                response.update({
                    "total": round(total, 2),
                    "count": count,
                    "avg": round(avg, 2),
                    "top": top_list
                })

        elif action == "get_rating":
            if not is_admin(user_id):
                response["message"] = "Только для администратора."
            else:
                period = payload.get("period")
                # Для простоты без периода
                masters_sum = {}
                for inc in data["incomes"]:
                    m = inc.get("master", "Неизвестно")
                    masters_sum[m] = masters_sum.get(m, 0) + inc["amount"]
                sorted_rating = sorted(masters_sum.items(), key=lambda x: x[1], reverse=True)[:20]
                rating_list = [{"name": m, "amount": round(s, 2)} for m, s in sorted_rating]
                response["rating"] = rating_list

        elif action == "get_pending":
            if not is_admin(user_id):
                response["message"] = "Только для администратора."
            else:
                pending = [p for p in data["pending"] if p.get("status") == "pending"]
                response["pending"] = pending

        elif action == "approve_request":
            if not is_admin(user_id):
                response["message"] = "Только для администратора."
            else:
                idx = payload.get("idx")
                if idx is not None and 0 <= idx < len(data["pending"]):
                    p = data["pending"][idx]
                    if p.get("status") == "pending":
                        p["status"] = "approved"
                        # Добавляем в incomes
                        data["incomes"].append({
                            "master": p["master"],
                            "branch": "Основной",  # упрощённо
                            "amount": p["amount"],
                            "date": datetime.now().isoformat(),
                            "text": p["text"]
                        })
                        save_data()
                        response["message"] = f"Заявка #{idx+1} подтверждена."
                    else:
                        response["message"] = "Заявка уже обработана."
                else:
                    response["message"] = "Неверный индекс."

        elif action == "reject_request":
            if not is_admin(user_id):
                response["message"] = "Только для администратора."
            else:
                idx = payload.get("idx")
                if idx is not None and 0 <= idx < len(data["pending"]):
                    p = data["pending"][idx]
                    if p.get("status") == "pending":
                        p["status"] = "rejected"
                        save_data()
                        response["message"] = f"Заявка #{idx+1} отклонена."
                    else:
                        response["message"] = "Заявка уже обработана."
                else:
                    response["message"] = "Неверный индекс."

        elif action == "change_request":
            if not is_admin(user_id):
                response["message"] = "Только для администратора."
            else:
                idx = payload.get("idx")
                new_amount = payload.get("amount")
                if idx is not None and 0 <= idx < len(data["pending"]):
                    p = data["pending"][idx]
                    if p.get("status") == "pending":
                        p["amount"] = new_amount
                        save_data()
                        response["message"] = f"Сумма заявки #{idx+1} изменена на {new_amount}."
                    else:
                        response["message"] = "Заявка уже обработана."
                else:
                    response["message"] = "Неверный индекс."

        elif action == "get_balances":
            if not is_admin(user_id):
                response["message"] = "Только для администратора."
            else:
                balances = []
                for master in data["masters"]:
                    name = master["name"]
                    bal = get_balance(name)
                    balances.append({"master": name, "balance": round(bal, 2)})
                response["balances"] = balances

        elif action == "make_payment":
            if not is_admin(user_id):
                response["message"] = "Только для администратора."
            else:
                master = payload.get("master")
                amount = float(payload.get("amount", 0))
                comment = payload.get("comment", "")
                if amount <= 0:
                    response["message"] = "Сумма должна быть положительной."
                else:
                    bal = get_balance(master)
                    if amount > bal:
                        response["message"] = f"Недостаточно средств. Баланс {bal:.2f}."
                    else:
                        data["payments"].append({
                            "master": master,
                            "amount": amount,
                            "date": datetime.now().isoformat(),
                            "comment": comment
                        })
                        save_data()
                        response["success"] = True
                        response["message"] = f"Выплата {amount:.2f} руб. мастеру {master} выполнена."

        await update.message.reply_text(json.dumps(response, ensure_ascii=False))

    except Exception as e:
        logger.error(f"Ошибка в web_app_data: {e}")
        await update.message.reply_text(json.dumps({"action": "error", "message": str(e)}))

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Неизвестная команда. Используйте /start.")

# ---------- Запуск ----------
def main():
    if not TOKEN:
        logger.error("Не задан BOT_TOKEN")
        sys.exit(1)

    # Создаём приложение
    app = Application.builder().token(TOKEN).build()

    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))

    # Настройка webhook
    if WEBHOOK_URL:
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
        )
    else:
        # Запуск с polling (для локальной разработки)
        logger.info("Запуск в режиме polling (без webhook)")
        app.run_polling()

if __name__ == "__main__":
    main()
