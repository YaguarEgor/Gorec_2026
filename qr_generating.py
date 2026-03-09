import random
import qrcode
import os


GIFTS = [
    "книга",
    "кружка",
    "подписка",
    "монополия",
    "настольная игра",
    "флешка",
    "футболка",
    "мышка",
    "клавиатура",
    "колонка",
    "термокружка",
    "картина",
    "фигурка",
    "лампа",
    "подушка",
    "подарочная карта"
]

DESCRIPTIONS = [
    "с индивидуальным дизайном",
    "с забавной надписью",
    "для ежедневного использования",
    "для работы и учёбы",
    "для настоящих гиков",
    "с возможностью персонализации",
    "для уютных вечеров дома",
    "для продуктивной работы",
    "для творческих людей",
    "для тех, кто ценит комфорт",
    "для тех, кто любит порядок",
    "для долгих зимних вечеров",
    "для путешествий и поездок",
    "для тех, кто много работает за компьютером",
    "для ценителей минимализма",
    "для хорошего настроения каждый день"
]

ADJECTIVES = [
    "крутая",
    "оригинальная",
    "полезная",
    "стильная",
    "прикольная",
    "удобная",
    "незабываемая",
    "яркая",
    "интересная",
    "современная",
    "минималистичная",
    "технологичная",
    "качественная",
    "компактная",
    "универсальная",
    "элегантная"
]


def generate_custom_qr(
    text,
    filename="QR/custom_qr.png",
    box_size=10,
    border=4,
    fill_color="black",
    back_color="white",
    version=None,
):
    qr = qrcode.QRCode(
        version=version,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )

    qr.add_data(text)
    qr.make(fit=True)

    img = qr.make_image(fill_color=fill_color, back_color=back_color)

    os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else ".", exist_ok=True)
    img.save(filename)
    return img


def generate_unique_combinations(n: int) -> list[str]:
    max_combinations = len(GIFTS) * len(ADJECTIVES) * len(DESCRIPTIONS)
    if n > max_combinations:
        raise ValueError(f"Максимально возможное число комбинаций: {max_combinations}")

    all_indices = [
        (i, j, k)
        for i in range(len(GIFTS))
        for j in range(len(ADJECTIVES))
        for k in range(len(DESCRIPTIONS))
    ]
    random.shuffle(all_indices)
    chosen = all_indices[:n]

    result = []
    for i, j, k in chosen:
        phrase = f"{ADJECTIVES[j]} {GIFTS[i]} {DESCRIPTIONS[k]}"
        result.append(phrase)
    return result


def generate_random_qr_text() -> str:
    return (
        f"{random.choice(ADJECTIVES)} "
        f"{random.choice(GIFTS)} "
        f"{random.choice(DESCRIPTIONS)}"
    )