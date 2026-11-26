def merge_ranges(ranges):
    merged = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            previous_start, previous_end = merged.pop()
            merged.append((previous_start, max(previous_end, end)))
        else:
            merged.append((start, end))
    return merged
