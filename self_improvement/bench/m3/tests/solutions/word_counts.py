from collections import Counter
import re

def top_words(text, limit):
    counts = Counter(word.lower() for word in re.findall(r"[A-Za-z]+", text))
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
