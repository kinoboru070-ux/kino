import os
import asyncio
import secrets
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.requests import Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ConversationHandler, CallbackContext, CallbackQueryHandler
)
from dotenv import load_dotenv

from config import BOT_TOKEN, ADMIN_ID
from database import (
    init_db, register_user_start, get_all_user_ids,
    add_series, get_all_series, get_series_id_by_name,
    add_episode, get_episode_by_code, get_episode_by_serial_and_number,
    get_episodes_count, get_free_episodes_count, set_free_episodes_count,
    is_user_subscribed, set_subscription, remove_subscription, get_all_subscribed_users,
    get_button_links, set_button_links,
    get_ad, remove_ad, increment_ad_count,
    create_referral, check_referral_code, get_all_referrals
)

load_dotenv()

# -------------------- Holatlar --------------------
WAITING_SERIES_NAME = 1
WAITING_EPISODE_NUMBER = 2
WAITING_VIDEO_FILE = 3
WAITING_DESCRIPTION = 4
WAITING_FREE_COUNT = 5
WAITING_INSTAGRAM_LINK = 6
WAITING_TELEGRAM_LINK = 7
WAITING_BROADCAST = 8
WAITING_REF_NAME = 9
WAITING_AD_CONTENT = 10
WAITING_BULK_SERIES_ID = 11
WAITING_BULK_VIDEO = 12
WAITING_BULK_DONE = 13

# -------------------- Webhook --------------------
WEBHOOK_PATH = "/webhook"
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if not RENDER_EXTERNAL_HOSTNAME:
    raise ValueError("RENDER_EXTERNAL_HOSTNAME topilmadi")
WEBHOOK_URL = f"https://{RENDER_EXTERNAL_HOSTNAME}{WEBHOOK_PATH}"

# -------------------- Reklama --------------------
async def send_ad_to_user(bot, chat_id):
    ad = await get_ad()
    if not ad:
        return
    content_type = ad["content_type"]
    file_id = ad["file_id"]
    text = ad["text"]
    caption = ad["caption"] or ""
    try:
        if content_type == "text":
            await bot.send_message(chat_id=chat_id, text=text)
        elif content_type == "photo":
            await bot.send_photo(chat_id=chat_id, photo=file_id, caption=caption)
        elif content_type == "video":
            await bot.send_video(chat_id=chat_id, video=file_id, caption=caption)
        elif content_type == "document":
            await bot.send_document(chat_id=chat_id, document=file_id, caption=caption)
        elif content_type == "audio":
            await bot.send_audio(chat_id=chat_id, audio=file_id, caption=caption)
        elif content_type == "voice":
            await bot.send_voice(chat_id=chat_id, voice=file_id, caption=caption)
        elif content_type == "animation":
            await bot.send_animation(chat_id=chat_id, animation=file_id, caption=caption)
        else:
            return
        await increment_ad_count()
    except Exception as e:
        print(f"Reklama yuborishda xatolik: {e}")

# -------------------- Serial epizodini ko‘rsatish --------------------
async def show_series_episodes(update: Update, context: CallbackContext, serial_id: int, episode_num: int = 1):
    user_id = update.effective_user.id
    series = await get_all_series()
    serial_name = next((s["name"] for s in series if s["id"] == serial_id), None)
    if not serial_name:
        await update.effective_message.reply_text("Serial topilmadi.")
        return

    total_episodes = await get_episodes_count(serial_id)
    if total_episodes == 0:
        await update.effective_message.reply_text("Bu serialda hali epizod yo‘q.")
        return

    if episode_num < 1:
        episode_num = 1
    elif episode_num > total_episodes:
        episode_num = total_episodes

    episode = await get_episode_by_serial_and_number(serial_id, episode_num)
    if not episode:
        await update.effective_message.reply_text("Epizod topilmadi.")
        return

    free_count = await get_free_episodes_count(serial_id)
    is_free = episode_num <= free_count
    if not is_free and not await is_user_subscribed(user_id):
        keyboard = [[InlineKeyboardButton("💰 Obuna bo‘lish", callback_data=f"subscribe_{serial_id}_{episode_num}")]]
        await update.effective_message.reply_text(
            f"⛔ Bu epizod (№{episode_num}) pullik.\n"
            f"Qolgan epizodlarni ko‘rish uchun obuna bo‘ling.\n"
            f"obuna narxi 10000 sum chekni adminga tashlang @coder070.\n"   
            f"6262570089299822 Agro bank uzkard URALOV. S.\n"
            f"OBUNA BUTUN UMIRGA QOLADI!!.\n"
            f"OBUNA BUTUN UMIRGA QOLADI!!.\n"
            "Quyidagi tugmani bosing va admin tasdiqlashini kuting.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    caption = f"🎬 {serial_name.upper()} – {episode_num}-epizod"
    if episode["description"]:
        caption += f"\n📖 {episode['description']}"

    try:
        await update.effective_message.reply_video(
            video=episode["file_id"],
            caption=caption,
            supports_streaming=True,
            protect_content=True
        )
    except Exception as e:
        await update.effective_message.reply_text("❌ Videoni yuborishda xatolik.")
        print(e)
        return

    nav_buttons = []
    if episode_num > 1:
        nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"ep_{serial_id}_{episode_num-1}"))
    else:
        nav_buttons.append(InlineKeyboardButton("◀️", callback_data="noop"))
    if episode_num < total_episodes:
        nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"ep_{serial_id}_{episode_num+1}"))
    else:
        nav_buttons.append(InlineKeyboardButton("▶️", callback_data="noop"))

    share_button = InlineKeyboardButton("📤 Jo‘natish", callback_data=f"share_{serial_id}_{episode_num}")
    links = await get_button_links()
    insta_button = InlineKeyboardButton("📱 Instagram", url=links["instagram_url"])
    tg_button = InlineKeyboardButton("📣 Telegram kanal", url=links["telegram_url"])

    keyboard = [
        nav_buttons,
        [share_button],
        [insta_button, tg_button]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.effective_message.reply_text(
        "Quyidagi tugmalar orqali boshqa epizodlarga o‘ting:",
        reply_markup=reply_markup
    )

async def show_episode_direct(update: Update, context: CallbackContext, serial_id: int, episode_num: int):
    user_id = update.effective_user.id
    series = await get_all_series()
    serial_name = next((s["name"] for s in series if s["id"] == serial_id), None)
    if not serial_name:
        await update.effective_message.reply_text("Serial topilmadi.")
        return

    episode = await get_episode_by_serial_and_number(serial_id, episode_num)
    if not episode:
        await update.effective_message.reply_text("Epizod topilmadi.")
        return

    free_count = await get_free_episodes_count(serial_id)
    is_free = episode_num <= free_count
    if not is_free and not await is_user_subscribed(user_id):
        keyboard = [[InlineKeyboardButton("💰 Obuna bo‘lish", callback_data=f"subscribe_{serial_id}_{episode_num}")]]
        await update.effective_message.reply_text(
            f"⛔ Bu epizod (№{episode_num}) pullik.\n"
            f"Qolgan epizodlarni ko‘rish uchun obuna bo‘ling.\n"
            f"obuna narxi 10000 SUM chekni adminga tashlang @coder070.\n"
            f"6262570089299822 Agro bank uzkard URALOV. S.\n"
            f"OBUNA BUTUN UMIRGA QOLADI!!.\n"
            "Quyidagi tugmani bosing va admin tasdiqlashini kuting.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    caption = f"🎬 {serial_name.upper()} – {episode_num}-epizod"
    if episode["description"]:
        caption += f"\n📖 {episode['description']}"

    try:
        await update.effective_message.reply_video(
            video=episode["file_id"],
            caption=caption,
            supports_streaming=True,
            protect_content=True
        )
    except Exception as e:
        await update.effective_message.reply_text("❌ Videoni yuborishda xatolik.")
        print(e)
        return

    total_episodes = await get_episodes_count(serial_id)
    nav_buttons = []
    if episode_num > 1:
        nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"ep_{serial_id}_{episode_num-1}"))
    else:
        nav_buttons.append(InlineKeyboardButton("◀️", callback_data="noop"))
    if episode_num < total_episodes:
        nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"ep_{serial_id}_{episode_num+1}"))
    else:
        nav_buttons.append(InlineKeyboardButton("▶️", callback_data="noop"))

    share_button = InlineKeyboardButton("📤 Jo‘natish", callback_data=f"share_{serial_id}_{episode_num}")
    links = await get_button_links()
    insta_button = InlineKeyboardButton("📱 Instagram", url=links["instagram_url"])
    tg_button = InlineKeyboardButton("📣 Telegram kanal", url=links["telegram_url"])

    keyboard = [
        nav_buttons,
        [share_button],
        [insta_button, tg_button]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.effective_message.reply_text(
        "Quyidagi tugmalar orqali boshqa epizodlarga o‘ting:",
        reply_markup=reply_markup
    )

# -------------------- Start --------------------
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    referral_code = context.args[0] if context.args else None
    await register_user_start(user_id, referral_code)

    series_list = await get_all_series()
    if not series_list:
        await update.message.reply_text("🎬 Hozircha hech qanday serial mavjud emas.")
        await send_ad_to_user(context.bot, user_id)
        return

    buttons = []
    row = []
    for idx, s in enumerate(series_list, start=1):
        row.append(InlineKeyboardButton(s["name"], callback_data=f"series_{s['id']}"))
        if idx % 2 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(
        "📽 **Mavjud seriallar:**\n\n"
        "Quyidagi seriallardan birini tanlang yoki epizod kodini raqamda yuboring.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    await send_ad_to_user(context.bot, user_id)

# -------------------- Callback handler --------------------
async def callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("series_"):
        serial_id = int(data.split("_")[1])
        await show_series_episodes(update, context, serial_id, 1)

    elif data.startswith("ep_"):
        parts = data.split("_")
        if len(parts) != 3:
            return
        serial_id = int(parts[1])
        episode_num = int(parts[2])
        await show_series_episodes(update, context, serial_id, episode_num)

    elif data.startswith("subscribe_"):
        parts = data.split("_")
        if len(parts) != 3:
            return
        serial_id = int(parts[1])
        episode_num = int(parts[2])
        user = update.effective_user
        username = f"@{user.username}" if user.username else f"ID: {user.id}"
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📩 Obuna so‘rovi:\n"
                 f"Foydalanuvchi: {username} (ID: {user.id})\n"
                 f"Serial ID: {serial_id}, epizod: {episode_num}\n"
                 f"Narxi: 10000 so‘m\n"
                 f"Admin: @coder070\n"
                 f"Tasdiqlash uchun: /confirm {user.id}"
        )
        await query.edit_message_text(
            "✅ So‘rovingiz adminga yuborildi. Iltimos, tasdiqlanishini kuting.\n"
            "Admin tasdiqlagandan so‘ng qaytadan /start bosing yoki epizodni qayta yuklang."
        )

    elif data.startswith("share_"):
        parts = data.split("_")
        if len(parts) != 3:
            return
        serial_id = int(parts[1])
        episode_num = int(parts[2])
        series = await get_all_series()
        serial_name = next((s["name"] for s in series if s["id"] == serial_id), "noma'lum")
        ep = await get_episode_by_serial_and_number(serial_id, episode_num)
        code = ep["code"] if ep else "?"
        await query.edit_message_text(
            f"🔗 {serial_name} – {episode_num}-epizod kod:\n"
            f"Botga ushbu raqamni yuboring: `{code}`\n"
            "Do‘stingiz ushbu kodni botga yuborib, epizodni ko‘rishi mumkin.",
            parse_mode="Markdown"
        )

    elif data == "noop":
        await query.answer("Bu yerda hech narsa yo‘q.")

# -------------------- Matnli xabar (raqamli kod) --------------------
async def handle_text(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ Iltimos, faqat raqamlardan iborat kod yuboring.")
        return

    code = int(text)
    episode = await get_episode_by_code(code)
    if not episode:
        await update.message.reply_text(f"❌ {code} kodli epizod topilmadi.")
        return

    serial_id = episode["serial_id"]
    episode_num = episode["episode_number"]
    await show_episode_direct(update, context, serial_id, episode_num)

# ==================== ADMIN BUYRUKLARI ====================

async def admin(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Siz admin emassiz!")
        return
    await update.message.reply_text(
        "<b>🔧 Admin panel</b>\n\n"
        "📌 Serial boshqaruvi:\n"
        "/add_series - yangi serial qo'shish\n"
        "/add_episode - bitta epizod qo'shish (serial ID, raqam, video)\n"
        "/add_bulk - bir nechta epizodni birdan qo'shish (avtomatik raqamlanadi)\n"
        "/set_free &lt;serial_id&gt; &lt;count&gt; - bepul epizodlar soni\n"
        "/list_series - barcha seriallar\n\n"
        "💰 Obuna boshqaruvi:\n"
        "/confirm &lt;user_id&gt; - obunani tasdiqlash\n"
        "/revoke &lt;user_id&gt; - obunani bekor qilish\n"
        "/subscribers - obunachilar ro‘yxati\n\n"
        "🔗 Tugma havolalari:\n"
        "/set_links - Instagram va Telegram havolalarini o‘rnatish\n\n"
        "📢 Broadcast:\n"
        "/broadcast - barchaga xabar yuborish\n\n"
        "📛 Referal:\n"
        "/createref - referal havola yaratish\n"
        "/refstats - referallar statistikasi\n\n"
        "📣 Reklama:\n"
        "/setad - reklama o‘rnatish\n"
        "/removead - reklamani o‘chirish\n"
        "/adstats - reklama statistikasi",
        parse_mode="HTML"
    )

# -------------------- add_series --------------------
async def add_series_start(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    await update.message.reply_text("📝 Yangi serial nomini kiriting:")
    return WAITING_SERIES_NAME

async def add_series_name(update: Update, context: CallbackContext):
    name = update.message.text.strip()
    serial_id = await add_series(name)
    await update.message.reply_text(f"✅ Serial qo‘shildi!\nID: {serial_id}\nNom: {name}\n\nEndi epizod qo‘shing: /add_episode yoki /add_bulk")
    return ConversationHandler.END

# -------------------- add_episode (single) --------------------
async def add_episode_start(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    series = await get_all_series()
    if not series:
        await update.message.reply_text("Hech qanday serial yo‘q. Avval /add_series bilan serial qo‘shing.")
        return ConversationHandler.END
    text = "Serial ID ni kiriting:\n"
    for s in series:
        text += f"ID: {s['id']} – {s['name']}\n"
    await update.message.reply_text(text)
    return WAITING_SERIES_NAME

async def add_episode_series_id(update: Update, context: CallbackContext):
    try:
        serial_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Iltimos, raqam kiriting.")
        return WAITING_SERIES_NAME
    series = await get_all_series()
    if not any(s["id"] == serial_id for s in series):
        await update.message.reply_text("❌ Bunday ID li serial topilmadi.")
        return WAITING_SERIES_NAME
    context.user_data["serial_id"] = serial_id
    await update.message.reply_text("🔢 Epizod raqamini kiriting (masalan: 1):")
    return WAITING_EPISODE_NUMBER

async def add_episode_number(update: Update, context: CallbackContext):
    try:
        ep_num = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Iltimos, raqam kiriting.")
        return WAITING_EPISODE_NUMBER
    context.user_data["episode_number"] = ep_num
    await update.message.reply_text("📹 Videoni yuboring (fayl sifatida):")
    return WAITING_VIDEO_FILE

async def add_episode_video(update: Update, context: CallbackContext):
    if not update.message.video:
        await update.message.reply_text("❌ Iltimos, video fayl yuboring.")
        return WAITING_VIDEO_FILE
    context.user_data["file_id"] = update.message.video.file_id
    await update.message.reply_text("✍️ Tavsif yozing (yoki /skip o‘tkazib yuboring):")
    return WAITING_DESCRIPTION

async def add_episode_description(update: Update, context: CallbackContext):
    context.user_data["description"] = update.message.text
    await finish_add_episode(update, context)
    return ConversationHandler.END

async def add_episode_skip(update: Update, context: CallbackContext):
    context.user_data["description"] = ""
    await finish_add_episode(update, context)
    return ConversationHandler.END

async def finish_add_episode(update: Update, context: CallbackContext):
    serial_id = context.user_data["serial_id"]
    ep_num = context.user_data["episode_number"]
    file_id = context.user_data["file_id"]
    desc = context.user_data.get("description", "")

    free_count = await get_free_episodes_count(serial_id)
    is_free = ep_num <= free_count

    code = await add_episode(serial_id, ep_num, file_id, desc, is_free)
    await update.message.reply_text(
        f"✅ Epizod saqlandi!\n"
        f"Serial ID: {serial_id}\n"
        f"Epizod: {ep_num}\n"
        f"Kod: {code}\n"
        f"Holat: {'Bepul' if is_free else 'Pullik'}"
    )

# -------------------- add_bulk --------------------
async def add_bulk_start(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    series = await get_all_series()
    if not series:
        await update.message.reply_text("Hech qanday serial yo‘q. Avval /add_series bilan serial qo‘shing.")
        return ConversationHandler.END
    text = "📌 Qaysi serialga epizod qo‘shmoqchisiz? Serial ID ni kiriting:\n"
    for s in series:
        text += f"ID: {s['id']} – {s['name']} (jami {await get_episodes_count(s['id'])} epizod)\n"
    await update.message.reply_text(text)
    return WAITING_BULK_SERIES_ID

async def add_bulk_series_id(update: Update, context: CallbackContext):
    try:
        serial_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Iltimos, raqam kiriting.")
        return WAITING_BULK_SERIES_ID
    series = await get_all_series()
    if not any(s["id"] == serial_id for s in series):
        await update.message.reply_text("❌ Bunday ID li serial topilmadi.")
        return WAITING_BULK_SERIES_ID
    context.user_data["bulk_serial_id"] = serial_id
    context.user_data["bulk_videos"] = []
    await update.message.reply_text(
        "📹 Endi videolarni birma-bir yuboring.\n"
        "Har bir videodan keyin tavsif yozishingiz yoki /skip qilishingiz mumkin.\n"
        "Barcha videolarni yuborganingizdan so‘ng /done deb yozing."
    )
    await update.message.reply_text("Iltimos, birinchi videoni yuboring:")
    return WAITING_BULK_VIDEO

async def add_bulk_video(update: Update, context: CallbackContext):
    if not update.message.video:
        await update.message.reply_text("❌ Iltimos, video fayl yuboring.")
        return WAITING_BULK_VIDEO
    file_id = update.message.video.file_id
    context.user_data["bulk_temp_file"] = file_id
    await update.message.reply_text("✍️ Tavsif yozing (yoki /skip o‘tkazib yuboring):")
    return WAITING_BULK_DONE

async def add_bulk_description(update: Update, context: CallbackContext):
    desc = update.message.text
    file_id = context.user_data.get("bulk_temp_file")
    if not file_id:
        await update.message.reply_text("Xatolik, qaytadan videoni yuboring.")
        return WAITING_BULK_VIDEO
    context.user_data["bulk_videos"].append((file_id, desc))
    context.user_data["bulk_temp_file"] = None
    await update.message.reply_text(f"✅ {len(context.user_data['bulk_videos'])}-video saqlandi. Keyingi videoni yuboring yoki /done bosing.")
    return WAITING_BULK_VIDEO

async def add_bulk_skip(update: Update, context: CallbackContext):
    file_id = context.user_data.get("bulk_temp_file")
    if not file_id:
        await update.message.reply_text("Xatolik, qaytadan videoni yuboring.")
        return WAITING_BULK_VIDEO
    context.user_data["bulk_videos"].append((file_id, ""))
    context.user_data["bulk_temp_file"] = None
    await update.message.reply_text(f"✅ {len(context.user_data['bulk_videos'])}-video saqlandi (tavsifsiz). Keyingi videoni yuboring yoki /done bosing.")
    return WAITING_BULK_VIDEO

async def add_bulk_done(update: Update, context: CallbackContext):
    serial_id = context.user_data.get("bulk_serial_id")
    videos = context.user_data.get("bulk_videos", [])
    if not videos:
        await update.message.reply_text("❌ Hech qanday video yuklanmagan. Bekor qilindi.")
        return ConversationHandler.END

    total_existing = await get_episodes_count(serial_id)
    free_count = await get_free_episodes_count(serial_id)
    saved = 0
    for idx, (file_id, desc) in enumerate(videos, start=1):
        ep_num = total_existing + idx
        is_free = ep_num <= free_count
        code = await add_episode(serial_id, ep_num, file_id, desc, is_free)
        saved += 1
        await update.message.reply_text(f"✅ Epizod {ep_num} saqlandi (kod: {code})")

    await update.message.reply_text(
        f"🎉 Jami {saved} ta epizod qo‘shildi.\n"
        f"Serial ID: {serial_id}\n"
        f"Bepul qismlar soni: {free_count}\n"
        f"Endi foydalanuvchilar {total_existing+1}-epizoddan boshlab ko‘ra oladi."
    )
    context.user_data.clear()
    return ConversationHandler.END

# -------------------- set_free --------------------
async def set_free(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Ishlatish: /set_free <serial_id> <count>")
        return
    serial_id, count = int(args[0]), int(args[1])
    await set_free_episodes_count(serial_id, count)
    await update.message.reply_text(f"✅ Serial ID {serial_id} uchun bepul epizodlar soni {count} ga o‘rnatildi.")

# -------------------- list_series (admin) --------------------
async def list_series(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return
    series = await get_all_series()
    if not series:
        await update.message.reply_text("Hech qanday serial yo‘q.")
        return
    text = "📋 Seriallar:\n"
    for s in series:
        total = await get_episodes_count(s["id"])
        free = await get_free_episodes_count(s["id"])
        text += f"ID {s['id']}: {s['name']} (jami {total}, bepul {free})\n"
    await update.message.reply_text(text)

# -------------------- confirm / revoke / subscribers --------------------
async def confirm_sub(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return
    args = context.args
    if not args:
        await update.message.reply_text("Ishlatish: /confirm <user_id>")
        return
    user_id = int(args[0])
    await set_subscription(user_id, ADMIN_ID)
    await update.message.reply_text(f"✅ Foydalanuvchi {user_id} obunasi tasdiqlandi.")
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="🎉 Obunangiz tasdiqlandi! Endi barcha pullik epizodlarni ko‘rishingiz mumkin."
        )
    except:
        pass

async def revoke_sub(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return
    args = context.args
    if not args:
        await update.message.reply_text("Ishlatish: /revoke <user_id>")
        return
    user_id = int(args[0])
    await remove_subscription(user_id)
    await update.message.reply_text(f"❌ Foydalanuvchi {user_id} obunasi bekor qilindi.")
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="⛔ Obunangiz bekor qilindi. Endi pullik epizodlarni ko‘ra olmaysiz."
        )
    except:
        pass

async def subscribers(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return
    users = await get_all_subscribed_users()
    if not users:
        await update.message.reply_text("Hech qanday obunachi yo‘q.")
        return
    text = "👥 Obunachilar:\n" + "\n".join(str(uid) for uid in users)
    await update.message.reply_text(text)

# -------------------- set_links --------------------
async def set_links_start(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    await update.message.reply_text("📱 Instagram havolasini kiriting (masalan: https://instagram.com/yourpage):")
    return WAITING_INSTAGRAM_LINK

async def set_links_instagram(update: Update, context: CallbackContext):
    context.user_data["instagram"] = update.message.text.strip()
    await update.message.reply_text("📣 Telegram kanal havolasini kiriting (masalan: https://t.me/yourchannel):")
    return WAITING_TELEGRAM_LINK

async def set_links_telegram(update: Update, context: CallbackContext):
    telegram = update.message.text.strip()
    instagram = context.user_data.get("instagram", "")
    await set_button_links(instagram, telegram)
    await update.message.reply_text("✅ Havolalar saqlandi!")
    return ConversationHandler.END

# -------------------- broadcast --------------------
async def broadcast_start(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    await update.message.reply_text("📢 Xabaringizni yuboring.")
    return WAITING_BROADCAST

async def broadcast_send(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    msg = update.message
    user_ids = await get_all_user_ids()
    total = len(user_ids)
    progress = await msg.reply_text(f"📤 {total} ta foydalanuvchiga jo‘natish boshlandi...")
    asyncio.create_task(_broadcast_task(msg, progress, user_ids, total))
    return ConversationHandler.END

async def _broadcast_task(msg, progress, user_ids, total):
    semaphore = asyncio.Semaphore(25)
    async def send_to_user(uid):
        async with semaphore:
            try:
                await msg.copy(chat_id=uid)
            except:
                pass
    tasks = [asyncio.create_task(send_to_user(uid)) for uid in user_ids]
    await asyncio.gather(*tasks)
    await progress.edit_text(f"✅ Xabar {total} ta foydalanuvchiga yuborildi.")

# -------------------- referal --------------------
async def createref_start(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    await update.message.reply_text("🔗 Referal nomini kiriting:")
    return WAITING_REF_NAME

async def createref_get_name(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    name = update.message.text.strip()
    bot_username = "YOUR_BOT_USERNAME"  # o'zgartiring
    while True:
        code = secrets.token_hex(3)
        if not await check_referral_code(code):
            break
    await create_referral(name, code)
    link = f"https://t.me/{bot_username}?start={code}"
    await update.message.reply_text(f"✅ Havola yaratildi:\n{link}")
    return ConversationHandler.END

async def refstats(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return
    refs = await get_all_referrals()
    if not refs:
        await update.message.reply_text("Hech qanday referal yo‘q.")
        return
    text = "📊 Referallar:\n"
    for code, name, count in refs:
        text += f"• {name} (kod: {code}) – {count} ta\n"
    await update.message.reply_text(text)

# -------------------- ad --------------------
async def setad_start(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    await update.message.reply_text("📢 Reklama kontentini yuboring (matn, rasm, video...).")
    return WAITING_AD_CONTENT

async def setad_get_content(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    msg = update.message
    content_type = None
    file_id = None
    text = None
    caption = msg.caption or ""
    if msg.text and not msg.caption:
        content_type = "text"
        text = msg.text
    elif msg.photo:
        content_type = "photo"
        file_id = msg.photo[-1].file_id
    elif msg.video:
        content_type = "video"
        file_id = msg.video.file_id
    elif msg.document:
        content_type = "document"
        file_id = msg.document.file_id
    elif msg.audio:
        content_type = "audio"
        file_id = msg.audio.file_id
    elif msg.voice:
        content_type = "voice"
        file_id = msg.voice.file_id
    elif msg.animation:
        content_type = "animation"
        file_id = msg.animation.file_id
    else:
        await update.message.reply_text("❌ Qo‘llab-quvvatlanmaydigan tur.")
        return WAITING_AD_CONTENT
    await set_ad(content_type, file_id, text, caption)
    await update.message.reply_text(f"✅ Reklama saqlandi (turi: {content_type})")
    return ConversationHandler.END

async def removead(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return
    await remove_ad()
    await update.message.reply_text("🗑️ Reklama o‘chirildi.")

async def adstats(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return
    ad = await get_ad()
    if ad:
        await update.message.reply_text(f"📊 Reklama {ad['send_count']} marta yuborilgan.")
    else:
        await update.message.reply_text("📭 Reklama yo‘q.")

# -------------------- Cancel --------------------
async def cancel(update: Update, context: CallbackContext):
    context.user_data.clear()
    await update.message.reply_text("Bekor qilindi.")
    return ConversationHandler.END

# -------------------- Webhook --------------------
async def webhook_handler(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot_application.bot)
    await bot_application.process_update(update)
    return JSONResponse({"ok": True})

async def healthcheck(request: Request):
    return JSONResponse({"status": "ok"})

bot_application = None

async def main():
    global bot_application
    await init_db()
    bot_application = Application.builder().token(BOT_TOKEN).build()

    # Handlerlar
    bot_application.add_handler(CommandHandler("start", start))
    bot_application.add_handler(CommandHandler("admin", admin))
    bot_application.add_handler(CommandHandler("list_series", list_series))  # ✅ ENDI ANIQLANGAN
    bot_application.add_handler(CommandHandler("set_free", set_free))
    bot_application.add_handler(CommandHandler("confirm", confirm_sub))
    bot_application.add_handler(CommandHandler("revoke", revoke_sub))
    bot_application.add_handler(CommandHandler("subscribers", subscribers))
    bot_application.add_handler(CommandHandler("removead", removead))
    bot_application.add_handler(CommandHandler("adstats", adstats))
    bot_application.add_handler(CommandHandler("refstats", refstats))
    bot_application.add_handler(CommandHandler("cancel", cancel))

    # Conversation: add series
    add_series_conv = ConversationHandler(
        entry_points=[CommandHandler("add_series", add_series_start)],
        states={WAITING_SERIES_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_series_name)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    bot_application.add_handler(add_series_conv)

    # Conversation: add episode (single)
    add_episode_conv = ConversationHandler(
        entry_points=[CommandHandler("add_episode", add_episode_start)],
        states={
            WAITING_SERIES_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_episode_series_id)],
            WAITING_EPISODE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_episode_number)],
            WAITING_VIDEO_FILE: [MessageHandler(filters.VIDEO, add_episode_video)],
            WAITING_DESCRIPTION: [
                CommandHandler("skip", add_episode_skip),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_episode_description)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    bot_application.add_handler(add_episode_conv)

    # Conversation: bulk add episodes
    add_bulk_conv = ConversationHandler(
        entry_points=[CommandHandler("add_bulk", add_bulk_start)],
        states={
            WAITING_BULK_SERIES_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_bulk_series_id)],
            WAITING_BULK_VIDEO: [
                MessageHandler(filters.VIDEO, add_bulk_video),
                CommandHandler("done", add_bulk_done)
            ],
            WAITING_BULK_DONE: [
                CommandHandler("skip", add_bulk_skip),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_bulk_description)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    bot_application.add_handler(add_bulk_conv)

    # Conversation: set links
    set_links_conv = ConversationHandler(
        entry_points=[CommandHandler("set_links", set_links_start)],
        states={
            WAITING_INSTAGRAM_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_links_instagram)],
            WAITING_TELEGRAM_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_links_telegram)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    bot_application.add_handler(set_links_conv)

    # Conversation: broadcast
    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start)],
        states={WAITING_BROADCAST: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_send)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    bot_application.add_handler(broadcast_conv)

    # Conversation: referal
    ref_conv = ConversationHandler(
        entry_points=[CommandHandler("createref", createref_start)],
        states={WAITING_REF_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, createref_get_name)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    bot_application.add_handler(ref_conv)

    # Conversation: ad
    ad_conv = ConversationHandler(
        entry_points=[CommandHandler("setad", setad_start)],
        states={WAITING_AD_CONTENT: [MessageHandler(filters.ALL & ~filters.COMMAND, setad_get_content)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    bot_application.add_handler(ad_conv)

    # Callback query
    bot_application.add_handler(CallbackQueryHandler(callback_handler))

    # Matnli xabar (raqamli kod)
    bot_application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Webhook
    await bot_application.initialize()
    await bot_application.bot.set_webhook(WEBHOOK_URL)

    starlette_app = Starlette(debug=False, routes=[
        Route(WEBHOOK_PATH, webhook_handler, methods=["POST"]),
        Route("/healthcheck", healthcheck, methods=["GET"]),
    ])
    port = int(os.environ.get("PORT", 8080))
    print(f"✅ Bot ishga tushdi, webhook: {WEBHOOK_URL}")
    import uvicorn
    config = uvicorn.Config(starlette_app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
