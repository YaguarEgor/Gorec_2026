import random

import qrcode
import os


def generate_custom_qr(text, filename="QR/custom_qr.png",
                       box_size=10, border=4,
                       fill_color="black", back_color="white",
                       version=None):
    """
    Генератор QR-кода с расширенными настройками.
    """
    qr = qrcode.QRCode(
        version=version,
        error_correction=qrcode.constants.ERROR_CORRECT_M,  # Средняя коррекция
        box_size=box_size,
        border=border,
    )

    qr.add_data(text)
    qr.make(fit=True)

    img = qr.make_image(fill_color=fill_color, back_color=back_color)

    os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else '.', exist_ok=True)

    img.save(filename)
    return img


def generate_unique_combinations(n):
    max_combinations = len(gifts) * len(adjectives) * len(descriptions)
    if n > max_combinations:
        raise ValueError(f"Максимально возможное число комбинаций: {max_combinations}")

    all_indices = [
        (i, j, k)
        for i in range(len(gifts))
        for j in range(len(adjectives))
        for k in range(len(descriptions))
    ]
    random.shuffle(all_indices)
    chosen = all_indices[:n]

    result = []
    for i, j, k in chosen:
        phrase = f"{adjectives[j]} {gifts[i]} {descriptions[k]}"
        result.append(phrase)
    return result


if __name__ == "__main__":
    gifts = [
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
    descriptions = [
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
    adjectives = [
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
    texts = generate_unique_combinations(30)
    for i, text in enumerate(texts):
        generate_custom_qr(
            text,
            filename=f"QR/{text}.png",
            box_size=12,
            fill_color="#2E7D32",  # Зелёный
            back_color="#FFFFFF"
        )
