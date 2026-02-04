import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from config import Config
from database import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=Config.BOT_TOKEN)
dp = Dispatcher()
router = Router()

# ========== СОСТОЯНИЯ ==========
class AddSpotStates(StatesGroup):
    waiting_for_number = State()
    waiting_for_address = State()
    waiting_for_price = State()

class BookingStates(StatesGroup):
    waiting_for_hours = State()

# ========== КЛАВИАТУРЫ ==========
def get_main_menu(user_id=None):
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="🚗 Найти место"))
    builder.add(KeyboardButton(text="🏠 Мои места"))
    builder.add(KeyboardButton(text="📋 Мои брони"))
    builder.add(KeyboardButton(text="➕ Выложить место"))
    if user_id and db.is_admin(user_id):
        builder.add(KeyboardButton(text="👑 Админ"))
    builder.adjust(2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

def get_spots_keyboard(spots):
    builder = InlineKeyboardBuilder()
    for spot in spots:
        builder.add(InlineKeyboardButton(
            text=f"📍 {spot['spot_number']} - {spot['price_per_hour']}₽/ч",
            callback_data=f"view_spot_{spot['id']}"
        ))
    builder.adjust(1)
    return builder.as_markup()

# ========== КОМАНДЫ ==========
@router.message(CommandStart())
async def start(message: Message):
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    username = message.from_user.username
    
    db.register_user(user_id, full_name, username)
    
    await message.answer(
        f"👋 Привет, {full_name}!\n\n"
        f"Я бот для бронирования парковочных мест.\n\n"
        f"Что умею:\n"
        f"• 🚗 Найти свободное место\n"
        f"• 🏠 Сдать свое место\n"
        f"• 📋 Управлять бронированиями\n\n"
        f"Используй кнопки ниже:",
        reply_markup=get_main_menu(user_id)
    )

@router.message(Command("admin"))
async def admin_login(message: Message):
    parts = message.text.split()
    if len(parts) == 2 and parts[1] == Config.ADMIN_PASSWORD:
        user = db.get_user(message.from_user.id)
        if user:
            await message.answer(
                "✅ Вы вошли как администратор!\n"
                "Теперь у вас есть кнопка '👑 Админ' в меню.",
                reply_markup=get_main_menu(message.from_user.id)
            )
        else:
            await message.answer("Сначала зарегистрируйтесь через /start")
    else:
        await message.answer("Используйте: /admin qwerty123")

# ========== ГЛАВНОЕ МЕНЮ ==========
@router.message(F.text == "🚗 Найти место")
async def find_spots(message: Message):
    spots = db.get_spots(available_only=True)
    
    if not spots:
        await message.answer("😔 Пока нет свободных мест.")
        return
    
    text = "🏠 Доступные места:\n\n"
    for spot in spots:
        text += f"📍 <b>{spot['spot_number']}</b>\n"
        text += f"   Адрес: {spot['address']}\n"
        text += f"   Цена: {spot['price_per_hour']}₽/час\n"
        text += f"   Владелец: {spot['owner_name']}\n\n"
    
    await message.answer(text, reply_markup=get_spots_keyboard(spots))

@router.message(F.text == "🏠 Мои места")
async def my_spots(message: Message):
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь через /start")
        return
    
    spots = db.get_user_spots(user['id'])
    
    if not spots:
        await message.answer("У вас пока нет выложенных мест.")
        return
    
    text = "🏠 Ваши места:\n\n"
    for spot in spots:
        status = "✅ Свободно" if spot['is_available'] else "❌ Занято"
        text += f"📍 <b>{spot['spot_number']}</b>\n"
        text += f"   Адрес: {spot['address']}\n"
        text += f"   Цена: {spot['price_per_hour']}₽/час\n"
        text += f"   Статус: {status}\n\n"
    
    await message.answer(text)

@router.message(F.text == "📋 Мои брони")
async def my_bookings(message: Message):
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь через /start")
        return
    
    bookings = db.get_user_bookings(user['id'])
    
    if not bookings:
        await message.answer("У вас пока нет бронирований.")
        return
    
    text = "📋 Ваши бронирования:\n\n"
    for booking in bookings:
        text += f"📍 <b>{booking['spot_number']}</b>\n"
        text += f"   Адрес: {booking['address']}\n"
        text += f"   Часов: {booking['hours']}\n"
        text += f"   Сумма: {booking['total_price']}₽\n"
        text += f"   Владелец: {booking['spot_owner']}\n\n"
    
    await message.answer(text)

# ========== ВЫЛОЖИТЬ МЕСТО ==========
@router.message(F.text == "➕ Выложить место")
async def add_spot_start(message: Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь через /start")
        return
    
    await state.set_state(AddSpotStates.waiting_for_number)
    await message.answer(
        "Введите номер места (например: A1, B2, Парковка-1):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Отмена")]],
            resize_keyboard=True
        )
    )

@router.message(AddSpotStates.waiting_for_number)
async def process_spot_number(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=get_main_menu(message.from_user.id))
        return
    
    await state.update_data(spot_number=message.text)
    await state.set_state(AddSpotStates.waiting_for_address)
    await message.answer("Введите адрес места:")

@router.message(AddSpotStates.waiting_for_address)
async def process_spot_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text)
    await state.set_state(AddSpotStates.waiting_for_price)
    await message.answer("Введите цену за час (в рублях):")

@router.message(AddSpotStates.waiting_for_price)
async def process_spot_price(message: Message, state: FSMContext):
    try:
        price = int(message.text)
        if price <= 0:
            await message.answer("Цена должна быть больше 0. Введите снова:")
            return
        
        data = await state.get_data()
        user = db.get_user(message.from_user.id)
        
        spot_id = db.add_spot(
            user['id'],
            data['spot_number'],
            data['address'],
            price
        )
        
        await message.answer(
            f"✅ Место добавлено!\n\n"
            f"📍 Номер: {data['spot_number']}\n"
            f"🏠 Адрес: {data['address']}\n"
            f"💰 Цена: {price}₽/час\n\n"
            f"Теперь другие пользователи могут его забронировать.",
            reply_markup=get_main_menu(message.from_user.id)
        )
        
        await state.clear()
        
    except ValueError:
        await message.answer("Введите число (например: 100):")

# ========== БРОНИРОВАНИЕ ==========
@router.callback_query(F.data.startswith("view_spot_"))
async def view_spot(callback: CallbackQuery, state: FSMContext):
    spot_id = int(callback.data.split("_")[2])
    spot = db.get_spot(spot_id)
    
    if not spot:
        await callback.answer("Место не найдено")
        return
    
    text = f"📍 <b>{spot['spot_number']}</b>\n"
    text += f"🏠 Адрес: {spot['address']}\n"
    text += f"💰 Цена: {spot['price_per_hour']}₽/час\n"
    text += f"👤 Владелец: {spot['owner_name']}\n\n"
    
    if spot['is_available']:
        text += "Для бронирования введите количество часов:"
        
        builder = InlineKeyboardBuilder()
        for hours in [1, 2, 3, 4, 6, 12, 24]:
            builder.add(InlineKeyboardButton(
                text=f"{hours} час.",
                callback_data=f"book_{spot_id}_{hours}"
            ))
        builder.adjust(3, 3, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    else:
        text += "❌ Это место уже забронировано"
        await callback.message.edit_text(text)
    
    await callback.answer()

@router.callback_query(F.data.startswith("book_"))
async def book_spot(callback: CallbackQuery):
    parts = callback.data.split("_")
    spot_id = int(parts[1])
    hours = int(parts[2])
    
    user = db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала зарегистрируйтесь")
        return
    
    spot = db.get_spot(spot_id)
    if not spot or not spot['is_available']:
        await callback.answer("Место уже занято")
        return
    
    booking_id = db.create_booking(user['id'], spot_id, hours)
    
    if booking_id:
        total_price = spot['price_per_hour'] * hours
        
        await callback.message.edit_text(
            f"✅ Вы забронировали место!\n\n"
            f"📍 {spot['spot_number']}\n"
            f"🏠 {spot['address']}\n"
            f"⏰ {hours} часов\n"
            f"💰 {total_price}₽\n\n"
            f"Свяжитесь с владельцем для уточнения деталей: @{spot['owner_telegram']}"
        )
        
        # Уведомляем владельца
        owner = db.get_user(spot['owner_telegram'])
        if owner:
            await bot.send_message(
                chat_id=owner['telegram_id'],
                text=f"📢 Ваше место забронировано!\n\n"
                     f"📍 {spot['spot_number']}\n"
                     f"👤 Клиент: {user['full_name']}\n"
                     f"⏰ {hours} часов\n"
                     f"💰 {total_price}₽\n\n"
                     f"Свяжитесь для подтверждения."
            )
    else:
        await callback.answer("Ошибка бронирования")
    
    await callback.answer()

# ========== АДМИН ПАНЕЛЬ ==========
@router.message(F.text == "👑 Админ")
async def admin_panel(message: Message):
    if not db.is_admin(message.from_user.id):
        await message.answer("❌ Доступ запрещен")
        return
    
    text = "👑 <b>Админ-панель</b>\n\n"
    text += "Выберите раздел:\n"
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="👥 Все пользователи", callback_data="admin_users"))
    builder.add(InlineKeyboardButton(text="🏠 Все места", callback_data="admin_spots"))
    builder.add(InlineKeyboardButton(text="📋 Все брони", callback_data="admin_bookings"))
    builder.add(InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"))
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "admin_users")
async def show_all_users(callback: CallbackQuery):
    users = db.get_all_users()
    
    text = "👥 <b>Все пользователи</b>\n\n"
    for user in users:
        admin = "👑" if user['is_admin'] else ""
        text += f"{admin} <b>{user['full_name']}</b>\n"
        text += f"   ID: {user['telegram_id']}\n"
        text += f"   @{user['username'] or 'нет'}\n"
        text += f"   📅 {user['created_at']}\n\n"
    
    await callback.message.edit_text(text)
    await callback.answer()

@router.callback_query(F.data == "admin_spots")
async def show_all_spots(callback: CallbackQuery):
    spots = db.get_all_spots_admin()
    
    text = "🏠 <b>Все места</b>\n\n"
    for spot in spots:
        status = "✅" if spot['is_available'] else "❌"
        text += f"{status} <b>{spot['spot_number']}</b>\n"
        text += f"   Адрес: {spot['address']}\n"
        text += f"   Цена: {spot['price_per_hour']}₽/ч\n"
        text += f"   Владелец: {spot['owner_name']}\n"
        text += f"   Бронирований: {spot['bookings_count'] or 0}\n"
        text += f"   Заработано: {spot['total_earnings'] or 0}₽\n\n"
    
    await callback.message.edit_text(text)
    await callback.answer()

@router.callback_query(F.data == "admin_bookings")
async def show_all_bookings(callback: CallbackQuery):
    bookings = db.get_all_bookings()
    
    text = "📋 <b>Все бронирования</b>\n\n"
    for booking in bookings:
        text += f"📍 <b>{booking['spot_number']}</b>\n"
        text += f"   Клиент: {booking['client_name']}\n"
        text += f"   Владелец: {booking['owner_name']}\n"
        text += f"   Часов: {booking['hours']}\n"
        text += f"   Сумма: {booking['total_price']}₽\n"
        text += f"   📅 {booking['created_at']}\n\n"
    
    await callback.message.edit_text(text)
    await callback.answer()

@router.callback_query(F.data == "admin_stats")
async def show_stats(callback: CallbackQuery):
    users = db.get_all_users()
    spots = db.get_all_spots_admin()
    bookings = db.get_all_bookings()
    
    total_earnings = sum(b['total_price'] for b in bookings)
    
    text = "📊 <b>Статистика системы</b>\n\n"
    text += f"👥 Пользователей: {len(users)}\n"
    text += f"🏠 Мест: {len(spots)}\n"
    text += f"📋 Бронирований: {len(bookings)}\n"
    text += f"💰 Общий доход: {total_earnings}₽\n"
    text += f"👑 Админов: {sum(1 for u in users if u['is_admin'])}\n"
    
    await callback.message.edit_text(text)
    await callback.answer()

# ========== ЗАПУСК ==========
async def main():
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())