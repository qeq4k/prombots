#!/usr/bin/env python3
"""
Скрипт для обновления ссылок на фильмы в базе данных.
"""

import sqlite3

DB_PATH = "movies.db"

# Новые ссылки на фильмы
NEW_LINKS = {
    "001": "https://rutube.ru/video/b711dccc1e09f21f5c38f7ede7942659",
    "002": "https://rutube.ru/video/6f8b51f26a15ce907dda2c7fbe3b9d75",
    "003": "https://rutube.ru/video/2224122c92a0a9a792d0d593b597a5c0",
    "004": "https://rutube.ru/video/a084ad5fc8b9f1b491f35d068845c3f6",
    "005": "https://rutube.ru/video/2f14b6a023091a7e8f0a817fea517942",
    "006": "https://rutube.ru/video/ec2c84b7047a31fc60773cbf756205b5",
    "007": "https://rutube.ru/video/6b5135798398073211926a779c3ca514",
    "008": "https://rutube.ru/video/f139d312af27ff7cfd5190fae2ab8a51",
    "009": "https://rutube.ru/video/bc8838bd8866ab712e672fcc38792f07",
    "010": "https://rutube.ru/video/9a528ca1bf29f6aae1b1c80cd6893140",
    "011": "https://rutube.ru/video/eb2dfc74eca23fa12c3488675268b52a",
    "012": "https://rutube.ru/video/858ddcb5ac64e39d6d22eca233b3dfad",
    "013": "https://rutube.ru/video/47e7ba138567a735a34e506f53ed0fcc",
    "014": "https://rutube.ru/video/9a528ca1bf29f6aae1b1c80cd6893140",
    "015": "https://rutube.ru/video/f54067045b42fa8e797c413208b56606",
    "016": "https://rutube.ru/video/fcafd479396e30b3ece0fa7bdeeca65f",
    "017": "https://rutube.ru/video/2c7b2a11e8cc4e33a1afe450115d17d9",
    "018": "https://rutube.ru/video/4399154391d0c5be082b11f1be2af00b",
    "019": "https://rutube.ru/video/0a5554d8121dac27c423a15bd202b553",
    "020": "https://rutube.ru/video/f54067045b42fa8e797c413208b56606",
    "021": "https://rutube.ru/video/26bcaa30858483da841dc8a211d9de3c",
    "022": "https://rutube.ru/video/ff6952901c159f808ed34fa689b201e0",
    "023": "https://rutube.ru/video/34c94490f0358a899d6eb20d4f33cfaa",
    "024": "https://rutube.ru/video/4282c18411899128b37d1dda827bef97",
    "025": "https://rutube.ru/video/5d357d6b9d00fdad10ceb11f6d07050a",
    "026": "https://rutube.ru/video/0b5824f152eebd7a67f1adef6f242c25",
    "027": "https://rutube.ru/video/99551ca91be3b24ef0f09b8851a9ce2e",
    "028": "https://rutube.ru/video/296d51d66a144cce0cd6ea48ec9156f8",
    "029": "https://rutube.ru/video/7c32c7a3b0e1acde2bdd5e8f7d95289a",
    "030": "https://rutube.ru/video/28343eeed565a4e1cc07902b81f4a623",
    "031": "https://rutube.ru/video/e5bd3e598b50fcba9cd93a50625af5bd",
    "032": "https://rutube.ru/video/d04cd4088ccd6fb9a70d44545679c59d",
    "033": "https://rutube.ru/video/7b7dc0afd1160051c068b8d84aca5b97",
    "034": "https://rutube.ru/video/d780470b45414d82d10dc91adb3eeff0",
    "035": "https://rutube.ru/video/40b56b5ae1575ab6cac048293cb30361",
    "036": "https://rutube.ru/video/fb96db79faa60c9a0a1ff43afb153feb",
    "037": "https://rutube.ru/video/063c127d114f229a337551da59b69475",
    "038": "https://rutube.ru/video/cabb2392e48f2f0b2308307362dac7de",
    "039": "https://rutube.ru/video/dbcb8baa45967aa057cbb467f7bf4108",
    "040": "https://rutube.ru/video/bd9a2d7574f20f7d56850684f5f075d2",
    "041": "https://rutube.ru/video/edbadb3c1ebb2cb6f0fa20e0eb0ecba5",
    "042": "https://rutube.ru/video/42fa711a9a58b96c19dda38b1300c440",
    "043": "https://rutube.ru/video/420e5e86c1062a61567ef3c9b369d926",
    "044": "https://rutube.ru/video/8c9190f8e2e8f9a4ccd2e636160accea",
    "045": "https://rutube.ru/video/7ffd17b1db213921a5a649aa8b83aa31",
    "046": "https://rutube.ru/video/4ea47a84dbc543846e337c2aec480902",
    "047": "https://rutube.ru/video/66fcb77822b541221b58ff1393955e55",
    "048": "https://rutube.ru/video/906488403f1d0f6654d4c7f78b629a80",
    "049": "https://rutube.ru/video/d9a5c046df3b2fbe5aa816785dd66aca",
    "050": "https://rutube.ru/video/26bcaa30858483da841dc8a211d9de3c",
    "051": "https://rutube.ru/video/413bac447799c7176268aeee63ba0760",
    "052": "https://my.mail.ru/mail/globous2018/video/7/14830.html",
}


def update_links():
    """Обновление ссылок в базе данных"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    updated = 0
    not_found = 0
    
    for code, new_link in NEW_LINKS.items():
        cursor.execute("SELECT id, title FROM movies WHERE code = ?", (code,))
        row = cursor.fetchone()
        
        if row:
            cursor.execute("UPDATE movies SET link = ? WHERE code = ?", (new_link, code))
            updated += 1
            print(f"✅ {code}. {row[1]} → ссылка обновлена")
        else:
            not_found += 1
            print(f"❌ {code}. Фильм не найден")
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ Готово!")
    print(f"Обновлено: {updated}")
    print(f"Не найдено: {not_found}")


if __name__ == "__main__":
    print("🔄 Обновление ссылок на фильмы...\n")
    update_links()
