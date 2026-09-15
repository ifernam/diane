class AlreadyInLiStrError(Exception):
    """A string is already in `LiStr`."""
    ...


class NotInLiStrError(Exception):
    """A string is not contained in `LiStr`."""
    ...


class LiStrIsEmptyError(Exception):
    """`LiStr` is empty."""
    ...


LiStr = list[str] | str


def add(liststr: LiStr, new: str) -> LiStr:
    """Add a string to a list of strings or a bare string (`LiStr`).

    Args:
        liststr (LiStr): A list of strings or a bare string.
        new (str): A new string.

    Returns:
        LiStr: An updated `LiStr`.
    """
    if isinstance(liststr, str):
        # A bare string.
        if new == liststr:
            raise AlreadyInLiStrError(f"'{new}' is already in the `LiStr`.")
        return [liststr, new]
    elif not liststr:
        # An empty list.
        return new
    else:
        # A non-empty list.
        if new in liststr:
            raise AlreadyInLiStrError(f"'{new}' is already in the `LiStr`.")
        return liststr + [new]


def remove(liststr: LiStr, old: str) -> LiStr:
    """Remove a string from a list of strings or a bare string
    (`LiStr`).

    Args:
        liststr (LiStr): A list of strings or a bare string.
        old (str): A string to be removed.

    Returns:
        LiStr: An updated `LiStr`.
    """
    if isinstance(liststr, str):
        # A bare string.
        if old == liststr:
            return []

        raise NotInLiStrError(
            f"The string '{old}' is not contained in the `LiStr`."
        )
    elif not liststr:
        # An empty list.
        raise LiStrIsEmptyError('The `LiStr` is empty.')
    else:
        # A non-empty list.
        if old not in liststr:
            raise NotInLiStrError(
                f"The string '{old}' is not contained in the `LiStr`."
            )

        updated = [s for s in liststr if s != old]
        if len(updated) == 1:
            return updated[0]
        else:
            return updated
