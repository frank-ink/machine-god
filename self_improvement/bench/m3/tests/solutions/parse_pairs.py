def parse(text):
    pairs = {}
    for field in text.split(";"):
        key, separator, value = field.partition("=")
        if separator and key.strip():
            pairs[key.strip()] = value.strip()
    return pairs
