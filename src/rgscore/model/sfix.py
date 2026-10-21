from functools import cache, reduce

from bitstring import BitArray, Bits


@cache
def __2pow(n) -> float | int:
    return pow(2, n)


def __to_bit_array(data: int | Bits) -> Bits:
    return BitArray(f"uint:8={data}") if isinstance(data, int) else data


def U(en: int, bit_arrays: list[Bits | int]) -> float | int:
    return reduce(
        lambda acc, v: acc + v, [__to_bit_array(a) for a in bit_arrays], BitArray.from_zeros(0)
    ).uint / __2pow(en)


def S(en: int, bit_arrays: list[Bits | int]) -> float | int:
    return reduce(
        lambda acc, v: acc + v,
        [__to_bit_array(a) for a in bit_arrays],
        BitArray.from_zeros(0),
    ).int / __2pow(en)
