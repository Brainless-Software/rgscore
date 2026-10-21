import dataclasses
import json
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from functools import reduce
from typing import Any, Self, final

from bitstring import BitArray
from i2c_api import I2CMaster, RegisterAddress
from pydantic import TypeAdapter


class RLink(ABC):
    @abstractmethod
    def read(self, addr: int, address_bus_width: int, value_width: int) -> BitArray | None:
        """
        Reads raw register value (of `value_width` bits) from address `addr` assuming that
        address bus is `address_bus_width`. If no register exist at this address, then returns None.
        """

    @abstractmethod
    def write(self, addr: int, address_bus_width: int, value: BitArray) -> bool:
        """
        Writes register value `value` to address `addr` assuming that address bus is `address_bus_width`.
        If register does exist at this address, then do write and return True, otherwise return False.
        """


@final
class RLinkI2C(RLink):
    def __init__(self, i2c: I2CMaster, device_address: int):
        self.i2c = i2c
        self.device_address = device_address

    def read(self, addr: int, address_bus_width: int, width: int) -> BitArray | None:
        bytes_to_read = int(width / 8)
        if (width % 8) > 0:
            bytes_to_read += 1

        data = self.i2c.read_register(
            address=self.device_address,
            register=RegisterAddress(addr, address_bus_width),
            num_bytes=bytes_to_read,
        )

        if data is None:
            return None
        else:
            return BitArray(data[0:width])

    def write(self, addr: int, address_bus_width: int, value: BitArray) -> bool:
        return self.i2c.write_register(
            address=self.device_address,
            register=RegisterAddress(addr, address_bus_width),
            data=value,
        )


@dataclass
class EnumValue:
    name: str
    value: float
    desc: str = ""

    def __post_init__(self):
        self.value = float(self.value)

    def __repr__(self) -> str:
        return f"{self.value} = {self.name} # {self.desc}"


@dataclass
class FieldDef:
    name: str
    offset: int
    signed: str
    width: int
    fractional: int
    rw: bool
    desc: str = ""
    enum_values: list[EnumValue] | None = None

    def __post_init__(self):
        self.__validate__()

    def __validate__(self):
        if self.signed not in ("U", "S"):
            raise ValueError("Invalid signed value")
        if self.offset < 0:
            raise ValueError("Field offset must be a positive integer")

        if self.enum_values is not None:
            vlen = len(self.enum_values)
            if len({v.name for v in self.enum_values}) < vlen or len({v.value for v in self.enum_values}) < vlen:
                raise ValueError("List of valid values contains duplicate entries")
            else:
                self.valid_name_values = {v.name: v for v in self.enum_values}
                self.valid_value_values = {v.value: v for v in self.enum_values}
        else:
            self.valid_name_values = {}
            self.valid_value_values = {}

    def copy(self) -> Self:
        return dataclasses.replace(self)

    def range(self) -> tuple[float, float]:
        if self.signed == "U":
            return (0.0, (pow(2, self.width) - 1) / pow(2, self.fractional))
        else:
            return (
                -(pow(2, self.width - 1) / pow(2, self.fractional)),
                (pow(2, self.width - 1) - 1) / pow(2, self.fractional),
            )

    def end_offset(self) -> int:
        return self.offset + self.width - 1

    def idxs(self) -> list[int]:
        return list(range(self.offset, self.end_offset() + 1))

    def format(self, value: float) -> str:
        return f"{int(value)}" if self.fractional == 0 else f"{value}"

    def __repr__(self):
        rw = "rw" if self.rw else "ro"
        return f"{self.name}@[{self.end_offset()}:{self.offset}]{self.signed}{self.width}.{self.fractional}#{rw}"

    def read_raw(self, data: BitArray) -> BitArray:
        return data[(len(data) - self.end_offset() - 1) : (len(data) - self.offset)]

    def next_up_value(self, data: BitArray) -> float | int:
        return self.__next(data, 1)

    def next_down_value(self, data: BitArray) -> float | int:
        return self.__next(data, -1)

    def __get_next_raw_field(self, data: BitArray, step: int) -> BitArray:
        raw_field = self.read_raw(data)
        try:
            if self.signed == "S":
                next_in_val = raw_field.int + step
                return BitArray(f"int:{len(raw_field)}={next_in_val}")
            else:  # unsigned
                next_in_val = raw_field.uint + step
                return BitArray(f"uint:{len(raw_field)}={next_in_val}")
        except ValueError:
            # we are here if next value is out of range for this field
            return raw_field

    def __next(self, data: BitArray, step: int) -> float | int:
        return self.__read_from_raw_field(self.__get_next_raw_field(data, step))

    def __read_from_raw_field(self, raw_field: BitArray) -> float | int:
        if self.fractional == 0:
            return raw_field.int if self.signed == "S" else raw_field.uint
        else:
            return (raw_field.int if self.signed == "S" else raw_field.uint) / pow(2, self.fractional)

    def read(self, data: BitArray) -> float | int:
        return self.__read_from_raw_field(self.read_raw(data))

    def write(self, data: BitArray, value: float) -> None:
        new_val = int(value * pow(2, self.fractional))
        tspec = ("int:" if self.signed == "S" else "uint:") + f"{self.width}={new_val}"
        data.overwrite(len(data) - self.end_offset() - 1, BitArray(tspec))

    @staticmethod
    def value_of(field_definition: str) -> "FieldDef":
        m = Register.field_def_re.match(field_definition)
        if m:
            end_offset = int(m.group("end"))

            start_group = m.group("start")
            start_offset = int(start_group) if start_group else end_offset

            implied_width = end_offset - start_offset + 1
            width = int(m.group("w"))
            if implied_width != width:
                raise ValueError(f"Inconsistent field width {implied_width} != {width}")
            rw = m.group("rw")
            rw = rw if rw else "rw"
            return FieldDef(
                name=m.group("name"),
                offset=start_offset,
                signed=m.group("s"),
                width=width,
                fractional=int(m.group("f")),
                rw=(rw == "rw"),
            )
        else:
            raise ValueError(f"Invalid register field definition [{field_definition}]")

    def with_description(self, desc: str) -> Self:
        self.desc = desc
        return self

    def with_enum(self, values: list[EnumValue]) -> Self:
        if len({v.name for v in values}) != len(values):
            raise ValueError("Duplicate name in enum values")
        if len({v.value for v in values}) != len(values):
            raise ValueError("Duplicate value in enum values")
        self.enum_values = values
        self.__validate__()
        return self


class Register:
    numeric_type_re = re.compile(r"^\s*(?P<s>U|S)(?P<w>\d+)\.(?P<f>\d+)\s*$")
    rw_re = re.compile(r"^\s*(?P<rw>rw|ro)\s*$")
    field_def_re = re.compile(
        r"^(?P<name>[a-zA-Z_]+[0-9]*)@\[(?P<end>\d+)(:(?P<start>\d+))?\](?P<s>U|S)(?P<w>\d+)\.(?P<f>\d+)(#(?P<rw>rw|ro))?$"
    )
    register_name_re = re.compile("^[a-zA-Z]+[a-zA-Z0-9_]*$")

    def __init__(
        self,
        bit_len: int,
        model: list[FieldDef] | None = None,
        address: int | None = None,
        address_bus_width_bytes: int = 1,
        name: str | None = None,
        link_provider: Callable[[], RLink] | None = None,
        desc: str = "",
    ):
        """
        Register in an object that encapsulates array of bits and field definitions and provides read and write
        access to these fields. Fields are defined in the model

        Args:
            bit_len: width of register in bits
            model: model of register fields
            address: register address (optional)
            address_bus_width_bytes: width of address bus in bytes
            name: register name (optional)
            link_provider: provider of link to the external storage (optional)
            desc: register description (optional)
        """
        if name is not None and not Register.register_name_re.match(name):
            raise ValueError("Invalid register name.")

        if bit_len <= 0:
            raise ValueError("Register width must be greater than zero")
        self.data: BitArray = BitArray.from_zeros(bit_len)
        self._originial_data = BitArray.from_zeros(bit_len)
        self.__width = bit_len
        self.__desc = desc

        self._model = (
            [FieldDef.value_of(f"val@[{bit_len - 1}:0]U{bit_len}.0")] if model is None else [m.copy() for m in model]
        )
        self._model.sort(key=lambda fd: -fd.offset)

        if self._model == []:
            raise ValueError(
                "Register model must not be empty list. Leaving it None will create an implicit field though."
            )
        self._fields_by_name: dict[str, FieldDef] = {fd.name: fd for fd in self._model}
        if len(self._fields_by_name) != len(self._model):
            raise ValueError("Duplicate field names in the model")
        self.__validate_model_wrt_width(self._model, self.width)
        self.__validate_fields_overlapp(self._model)

        self.address = address
        self.address_bus_width_bytes = address_bus_width_bytes
        self.name = name
        self.__link_provider: Callable[[], RLink] | None = link_provider
        self.linked_address: int | None = address

    def __validate_model_wrt_width(self, model: list[FieldDef], width: int):
        for m in model:
            if m.end_offset() >= width or m.offset < 0:
                raise ValueError(f'Field "{m.name}" extends outside of register width.')

    def __validate_fields_overlapp(self, model: list[FieldDef]):
        fields_idxs = reduce(lambda x, y: x + y, [m.idxs() for m in model], [])
        if len(set(fields_idxs)) != len(fields_idxs):
            raise ValueError("Overlapping fields in register definition.")

    @property
    def desc(self):
        return self.__desc

    @desc.setter
    def desc(self, desc: str):
        self.__desc = desc

    @property
    def width(self) -> int:
        return self.__width

    @width.setter
    def width(self, new_width: int):
        self.__validate_model_wrt_width(self._model, new_width)
        self.__width = new_width
        self._originial_data = BitArray.from_zeros(new_width)
        self.data = BitArray.from_zeros(new_width)

    def replace_model(self, new_model: list[FieldDef]):
        field_names: set[str] = {fd.name for fd in new_model}
        if len(field_names) != len(new_model):
            raise ValueError("Duplicate field names in the model")
        self.__validate_fields_overlapp(new_model)
        self.__validate_model_wrt_width(new_model, self.width)
        self._model.clear()
        self._model.extend(new_model)
        self._model.sort(key=lambda fd: -fd.offset)

    def copy(self) -> "Register":
        register_copy = Register(
            bit_len=self.width,
            model=[fd.copy() for fd in self._model],
            address=self.address,
            name=self.name,
            link_provider=self.__link_provider,
        )
        register_copy.data = self.data.copy()
        register_copy._originial_data = self._originial_data.copy()
        return register_copy

    def is_changed(self) -> bool:
        """
        Returns True or False indicating of register data has changed since it was loaded. This method is only usefull
        when external storage is linked to the register and read() and write() methods are called.
        """
        return self._originial_data != self.data

    def get_def(self) -> str:
        """Returns human-readable register definition."""
        return (
            "Register"
            + ("" if self.name is None else f" name:{self.name}")
            + ("" if self.address is None else f" addr:0x{self.address:X}")
            + ("" if self.desc == "" else f' desc:"{self.desc}"')
            + f" width:{self.width} fields:{self._model}"
        )

    def __repr__(self):
        retval = "Register" if self.name is None else self.name
        if self.address is not None:
            retval += f"[0x{self.address:0{self.address_bus_width_bytes * 2}X}]"
        return (
            f"{retval}("
            + ", ".join(
                [f"{field_def.name}={field_def.format(field_def.read(self.data))}" for field_def in self._model]
            )
            + ")"
        )

    def to_dict_def(self) -> dict:
        """Exports register definition as dict."""
        return {
            "name": self.name,
            "address": None if self.address is None else f"0x{self.address:X}",
            "address_bus_width_bytes": self.address_bus_width_bytes,
            "width": self.width,
            "desc": self.desc,
            "fields": [dataclasses.asdict(field_def) for field_def in self._model],
        }

    def to_json_def(self, indent: int | None = None) -> str:
        """Exports register definition as json text."""
        return json.dumps(self.to_dict_def(), indent=indent)

    @staticmethod
    def from_dict_def(data: dict) -> "Register":
        fd_adapter = TypeAdapter(FieldDef)
        return Register(
            bit_len=data["width"],
            name=data["name"],
            desc=data["desc"] if "desc" in data else "",
            address=None if data["address"] is None else int(data["address"], 16),
            address_bus_width_bytes=data["address_bus_width_bytes"],
            model=[fd_adapter.validate_python(f) for f in data["fields"]],
        )

    @staticmethod
    def from_json_def(json_str: str) -> "Register":
        """Imports register definition from json text and returns instance of Register."""
        return Register.from_dict_def(json.loads(json_str))

    def set_field_value(self, field: str, value: float | str) -> float | int:
        """
        Sets value to a field or raises exception if unable to do so. If value is str, then it is used as a look up
        into associated enum if any and found number value is used. If data in the register model in memory actually
        changed as a result of calling this method, then calling `Register::is_changed()` starts returning True.
        """
        field_def = self._fields_by_name.get(field)
        if field_def is None:
            raise ValueError(f'There is no field "{field}" in this register.')
        if not field_def.rw:
            raise ValueError(f'Field "{field}" is not writable.')

        def get_value() -> float:
            if isinstance(value, str):
                num_val = field_def.valid_name_values.get(value)
                if num_val is None:
                    raise ValueError(f"Invalid enum value [{value}] for field {field}")
                else:
                    return num_val.value
            else:
                return value

        value = get_value()
        min, max = field_def.range()
        if min <= value <= max:
            field_def.write(self.data, value)
            return field_def.read(self.data)
        else:
            raise ValueError(f'Value {value} is out of range [{field_def.range()}] for field "{field}"')

    def get_field_value(self, field: str) -> float | int:
        field_def = self._fields_by_name.get(field)
        if field_def is None:
            raise ValueError(f'There is no field "{field}" in this register.')
        else:
            return field_def.read(self.data)

    def get_next_up_field_value(self, field: str) -> float | int:
        field_def = self._fields_by_name.get(field)
        if field_def is None:
            raise ValueError(f'There is no field "{field}" in this register.')
        else:
            return field_def.next_up_value(self.data)

    def get_next_down_field_value(self, field: str) -> float | int:
        field_def = self._fields_by_name.get(field)
        if field_def is None:
            raise ValueError(f'There is no field "{field}" in this register.')
        else:
            return field_def.next_down_value(self.data)

    def get_field_value_raw(self, field: str) -> BitArray:
        field_def = self._fields_by_name.get(field)
        if field_def is None:
            raise ValueError(f'There is no field "{field}" in this register.')
        else:
            return field_def.read_raw(self.data)

    def get_field_values(self) -> dict[str, float]:
        return {m.name: self.get_field_value(m.name) for m in self._model}

    def get_field_definition(self, field: str) -> FieldDef:
        return self._fields_by_name[field]

    def get_field_names(self) -> list[str]:
        return [m.name for m in self._model]

    def link(self, link: RLink, register_address: int | None = None) -> None:
        """
        Links register to external store. If optional address is provided, then it will be used to access external store
        even if register has address in its definition. If optional address is not provided, then address defined in the
        register will be used. If no addresses are given and present in the internal register definition then ValueError
        will be raised.

        :param link: link to external store
        :param register_address: address of register in external store
        """
        if register_address is not None:
            self.linked_address = register_address
        if self.linked_address is None:
            raise ValueError(
                "To link register to external store address must be either set in the register "
                "or provided during linking."
            )
        self.__link_provider = lambda: link

    def set_link_provider(self, link_provider: Callable[[], RLink]) -> None:
        self.__link_provider = link_provider

    def read(self) -> None:
        """
        Reads register data from associated link (external store). If no link is configured, then this is a no-op.
        If external store store (link) is configure and read operation fails for any reason than RuntimeError is raised.
        Once data is read from the external store, calling `Register::is_changed()` starts returning False until
        data is modified by calling `Register::set_field_value(...)`.
        """
        if self.__link_provider is not None:
            assert self.linked_address is not None
            raw_data = self.__link_provider().read(self.linked_address, self.address_bus_width_bytes, self.width)
            if raw_data is None:
                raise RuntimeError(f"There is no register at the address {self.linked_address}.")
            self.data = raw_data
            self._originial_data = raw_data.copy()

    def write(self, read_back: bool = False, if_changed_only: bool = False) -> bool:
        """
        Writes register data to external store configured when `Register::link(...)` method is called.
        Once data is written to the external store, calling `Register::is_changed()` starts returning False until
        data is modified by calling `Register::set_field_value(...)`.

        :param read_back: If True, then immediately after write operation read it back. If False, then do just write op.
        :param if_changed_only: If True, then check if register in memory model changed and if so then do write,
                otherwise do not write (return False). If False (default), then always write.
        :return: True or False if write operation was successful or not.
        """
        if self.__link_provider is None or (if_changed_only and self._originial_data == self.data):
            return False
        else:
            assert self.linked_address is not None
            write_success = self.__link_provider().write(self.linked_address, self.address_bus_width_bytes, self.data)
            if read_back:
                self.read()
            if write_success:
                self._originial_data = self.data.copy()
            return write_success

    def mk_embedding_class(self, link_provider: Callable[[], RLink], auto_sync: bool) -> Any:
        register = self.copy()
        register.set_link_provider(link_provider)

        attrs = {
            "_read": register.read,
            "_write": register.write,
            "__repr__": register.__repr__,
            "__call__": lambda _: register.data,
        }
        for field_name in self.get_field_names():

            def mk_accessor(fname, register, auto_sync):
                def field_accessor(sself, new_value=None) -> int | float:
                    if new_value is None:
                        if auto_sync:
                            register.read()
                        return register.get_field_value(fname)
                    else:
                        retval = register.set_field_value(fname, new_value)
                        if auto_sync:
                            register.write()
                        return retval

                return field_accessor

            def mk_raw_accessor(fname, register):
                def field_accessor(sself) -> BitArray:
                    if auto_sync:
                        register.read()
                    return register.get_field_value_raw(fname)

                return field_accessor

            accessor = mk_accessor(field_name, register, auto_sync)
            attrs[field_name] = property(fget=accessor, fset=accessor)
            attrs[field_name + "_raw"] = property(fget=mk_raw_accessor(field_name, register))

        return type(self.name, (), attrs)


def Field(
    name: str, offset: int, numeric_type: str, rw: str = "rw", desc: str = "", values: list[EnumValue] | None = None
) -> FieldDef:
    """
    Convinience method for creating instance of `FieldDef`.

    Args:
        name: field name
        offset: field offset from the right
        numeric_type: fixed point number type, e.g. U5.7 or S3.0 etc.
        rw: "rw" (default) or "ro" - read/write or read/only
        desc: optiona field description
        values: optional enum values

    Returns:
        Instance of `FieldDef`.
    """
    nt_m = Register.numeric_type_re.match(numeric_type)
    if nt_m is None:
        raise ValueError(f"Invalid numeric type: {numeric_type}")

    rw_m = Register.rw_re.match(rw)
    if rw_m is None:
        raise ValueError(f"Invalid rw: {rw}")

    return FieldDef(
        name=name,
        offset=offset,
        width=int(nt_m.group("w")),
        signed=nt_m.group("s"),
        fractional=int(nt_m.group("f")),
        rw=(rw == "rw"),
        desc=desc,
        enum_values=values,
    )
