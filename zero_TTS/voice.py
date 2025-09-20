from typing import List, Dict
import os
import config

from elevenlabs.client import ElevenLabs

API_KEY = getattr(config, "elevenlabs_api_key", None) or os.getenv("ELEVENLABS_API_KEY")
if not API_KEY:
    raise RuntimeError(
        "ELEVENLABS API key отсутствует: задайте config.elevenlabs_api_key "
        "или переменную окружения ELEVENLABS_API_KEY"
    )

client = ElevenLabs(api_key=API_KEY)

def get_all_voices() -> List[Dict[str, str]]:
    """
    Вернёт список голосов как [{name, id}, ...].
    Требует у API-ключа право voices_read. Если права нет — пробросит понятную ошибку.
    """
    try:
        resp = client.voices.get_all()
        return [{"name": v.name, "id": v.voice_id} for v in resp.voices]
    except Exception as e:
        # Частый случай: 401 missing_permissions: voices_read
        raise RuntimeError(
            "Не удалось получить список голосов (возможно, у ключа нет разрешения voices_read). "
            "Укажите ELEVENLABS_VOICE_ID в config.py или переменной окружения и используйте его напрямую."
        ) from e

def generate_audio(text: str, voice_id: str, filename: str = "audio.mp3") -> str:
    """
    Сгенерировать озвучку и сохранить в mp3.
    Работает на версиях SDK без top-level generate(): используем client.text_to_speech.convert().
    """
    if not text:
        raise ValueError("text пустой")
    if not voice_id:
        raise ValueError("voice_id пустой")

    # Универсальные параметры; output — итератор байтов
    audio_iter = client.text_to_speech.convert(
        voice_id=voice_id,
        model_id="eleven_multilingual_v2",
        text=text,
        output_format="mp3_44100_128",
    )

    # Сохраняем поток на диск
    with open(filename, "wb") as f:
        for chunk in audio_iter:
            f.write(chunk)

    return filename


