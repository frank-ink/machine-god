def encode(number):
    if not 1 <= number <= 3999:
        raise ValueError("out of range")
    result = []
    for value, symbol in [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),
                          (90,"XC"),(50,"L"),(40,"XL"),(10,"X"),(9,"IX"),
                          (5,"V"),(4,"IV"),(1,"I")]:
        count, number = divmod(number, value)
        result.append(symbol * count)
    return "".join(result)
