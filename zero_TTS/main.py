import io
import os
import shutil
import subprocess
import telebot

import config
from voice import get_all_voices, generate_audio

# ---------- Telegram ----------
API_TOKEN = getattr(config, "bot_token", None) or os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise RuntimeError("BOT_TOKEN отсутствует: задайте config.bot_token или переменную окружения BOT_TOKEN")

bot = telebot.TeleBot(API_TOKEN)

# ---------- Загрузка голосов ----------
# Фолбэк: если нет права voices_read, используем конкретный voice_id из конфига/окружения
fallback_voice_id = getattr(config, "elevenlabs_voice_id", None) or os.getenv("ELEVENLABS_VOICE_ID")

try:
    voices_list = get_all_voices()  # list[{"name","id"}]
except Exception as e:
    voices_list = []
    if not fallback_voice_id:
        raise
    # Сделаем один «виртуальный» пункт для клавиатуры
    voices_list = [{"name": "Default", "id": fallback_voice_id}]

voice_names = [v["name"] for v in voices_list]
name_to_id = {v["name"]: v["id"] for v in voices_list}

# ---------- Клавиатура ----------
voice_buttons = telebot.types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
for name in voice_names:
    voice_buttons.add(telebot.types.KeyboardButton(name))

# ---------- Хранилище выбранных голосов ----------
selected_voice: dict[int, str] = {}

# ---------- FFmpeg ----------
FFMPEG = shutil.which("ffmpeg") or r"C:\Users\valeri\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe"

def mp3_to_ogg_opus(mp3_path: str, bitrate: str = "64k") -> io.BytesIO:
    """
    Конвертирует mp3 -> ogg/opus для send_voice. Нужен установленный ffmpeg.
    Возвращает готовый BytesIO.
    """
    if not FFMPEG or not os.path.exists(FFMPEG):
        raise RuntimeError(
            "FFmpeg не найден. Установите его (winget install Gyan.FFmpeg) или укажите путь к ffmpeg.exe в переменной FFMPEG."
        )

    cmd = [
        FFMPEG, "-y",
        "-i", mp3_path,
        "-ac", "1",
        "-c:a", "libopus",
        "-b:a", bitrate,
        "-vbr", "on",
        "-f", "ogg",
        "pipe:1",
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(f"FFmpeg ошибка: {proc.stderr.decode('utf-8', errors='ignore')[:4000]}")

    buf = io.BytesIO(proc.stdout)
    buf.seek(0)
    return buf

# ---------- Хендлеры ----------
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        "Привет! Я бот для создания озвучки.\n"
        "Выбери голос, который будет использоваться при озвучке:",
        reply_markup=voice_buttons
    )

@bot.message_handler(func=lambda m: m.text in voice_names)
def voice_selected(message):
    user_id = message.from_user.id
    voice_name = message.text
    voice_id = name_to_id.get(voice_name)
    if not voice_id:
        bot.reply_to(message, "Не удалось найти выбранный голос. Попробуй /start ещё раз.")
        return
    selected_voice[user_id] = voice_id
    bot.reply_to(message, f"Вы выбрали голос: {voice_name}. Теперь отправьте текст для озвучки.")

@bot.message_handler(func=lambda m: True)
def generate_voice(message):
    user_id = message.from_user.id
    voice_id = selected_voice.get(user_id)

    if not voice_id:
        bot.reply_to(message, "Сначала выберите голос командой /start.")
        return

    text = message.text.strip()
    if not text:
        bot.reply_to(message, "Пустой текст. Введите текст для озвучки.")
        return

    try:
        # 1) Генерация MP3
        mp3_path = generate_audio(text, voice_id)

        # 2) Отправляем MP3-файл
        with open(mp3_path, "rb") as f:
            bot.send_audio(user_id, f, caption="Готово! Вот mp3-файл озвучки.")

        # 3) Конвертируем в OGG/Opus и отправляем как voice
        try:
            ogg_bytes = mp3_to_ogg_opus(mp3_path, bitrate="64k")
            bot.send_voice(user_id, ogg_bytes, caption="И это же — голосовое сообщение.")
        except Exception as conv_err:
            bot.send_message(user_id, f"Не удалось сформировать голосовое (OGG/Opus): {conv_err}")

        # При желании можно удалить временный mp3:
        # os.remove(mp3_path)

    except Exception as e:
        bot.reply_to(message, f"Ошибка при генерации аудио: {e}")

# ---------- Запуск ----------
if __name__ == '__main__':
    bot.polling(none_stop=True)
