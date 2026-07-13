def normalize_area_code(area_code: str | None) -> str:
    """
    Normalizes a fishing area code by converting to uppercase and stripping
    any spaces, hyphens, or underscores.
    Example: '471-011' -> '471011', '471 011' -> '471011', '  471_011 ' -> '471011'
    """
    if not area_code:
        return "XX"
    return (
        area_code.replace(" ", "")
        .replace("-", "")
        .replace("_", "")
        .upper()
        .strip()
    )
