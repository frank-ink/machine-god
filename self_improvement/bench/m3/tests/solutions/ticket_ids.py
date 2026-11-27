import re

def tickets(text):
    return re.findall(r"(?<!\w)[A-Z]{2,4}-[0-9]{2,5}(?!\w)", text)
