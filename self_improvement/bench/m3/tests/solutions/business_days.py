from datetime import date, timedelta

def advance(start, days, holidays=()):
    current = date.fromisoformat(start)
    closed = set(holidays)
    while days:
        current += timedelta(days=1)
        if current.weekday() < 5 and current.isoformat() not in closed:
            days -= 1
    return current.isoformat()
