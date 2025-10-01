import re


def create_object(results: list[dict]):
    seen = set()
    data = []
    pattern = re.compile(
        r"(\d{2}:\d{2})・[話語]者(\d+)(.*?)(?=\d{2}:\d{2}・[話語]者\d+|$)", re.DOTALL
    )

    for item in results:
        for match in pattern.finditer(item["text"]):
            time, speaker_id, body = match.groups()
            key = (time, speaker_id)
            if key not in seen:
                seen.add(key)
                text = re.sub(r"\s+", " ", body).strip()
                data.append(
                    {
                        "time": time,
                        "speaker": int(speaker_id),
                        "text": edit_text(text),
                    }
                )
    return data


def edit_text(text: str) -> str:
    text = re.sub(r"\d{2}:\d{2}", "", text)
    patterns = [
        (re.compile(r"(ヨウ|洋|耀)さん"), "陽さん"),
        (re.compile(r"(マイ|まい)さん"), "舞さん"),
        (re.compile(r"スタートFM"), "START/FM"),
    ]
    for pattern, replacement in patterns:
        text = pattern.sub(replacement, text)
    return text
