def ordinal(n):
    """
    Convert an integer to its ordinal representation.
    E.g., 1 -> '1st', 2 -> '2nd', etc.
    """
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    if n % 10 == 1:
        return f"{n}st"
    if n % 10 == 2:
        return f"{n}nd"
    if n % 10 == 3:
        return f"{n}rd"
    return f"{n}th"
