import dataclasses
import json
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from functools import reduce
from typing import Self, final

from bitstring import BitArray
from i2c_api import I2CMaster, RegisterAddress
from pydantic import TypeAdapter
from tabulate import tabulate


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
        return (
            self.i2c.write_register(
                address=self.device_address,
                register=RegisterAddress(addr, address_bus_width),
                data=value,
            )
            is not None
        )


enum_value_name_re = re.compile(r"^[a-zA-Z_][a-zA-Z_0-9]*$")


@dataclass(frozen=True)
class EnumValue:
    name: str
    value: float
    desc: str = ""

    def __post_init__(self):
        if not enum_value_name_re.match(self.name):
            raise ValueError(f"Invalid enum name [{self.name}]")

    def __repr__(self) -> str:
        return f"{self.name}({self.value})"


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

    def __eq__(self, other: object, /) -> bool:
        eq = (
            isinstance(other, FieldDef)
            and self.name == other.name
            and self.offset == other.offset
            and self.signed == other.signed
            and self.width == other.width
            and self.fractional == other.fractional
            and self.rw == other.rw
            and self.desc == other.desc
        )
        if not eq:
            return False
        elif self.enum_values is None and other.enum_values is None:
            return True
        elif self.enum_values is not None and other.enum_values is None:
            return False
        elif self.enum_values is None and other.enum_values is not None:
            return False
        else:
            return sorted(self.enum_values, key=lambda x: x.value) == sorted(other.enum_values, key=lambda x: x.value)

    def rw_mode(self) -> str:
        """Return r/w or r/o if this field is read/write or read/only."""
        return "r/w" if self.rw else "r/o"

    def __post_init__(self):
        self.__validate__()

    def num_type(self) -> str:
        """Returns fixed-point numerical type associatd with this field in the format (U|S)\\\\d+.\\\\d+"""
        return f"{self.signed}{self.width}.{self.fractional}"

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
        """Returns a copy of this field definition."""
        return dataclasses.replace(self)

    def range(self) -> tuple[float, float]:
        """Return inclusive range of possible values for this field."""
        if self.signed == "U":
            return (0.0, (pow(2, self.width) - 1) / pow(2, self.fractional))
        else:
            return (
                -(pow(2, self.width - 1) / pow(2, self.fractional)),
                (pow(2, self.width - 1) - 1) / pow(2, self.fractional),
            )

    def end_offset(self) -> int:
        """Returns inclusive end offset where this field ends in the larger bit array."""
        return self.offset + self.width - 1

    def idxs(self) -> list[int]:
        """Returns list of offset for each individual bits for this field."""
        return list(range(self.offset, self.end_offset() + 1))

    def format(self, value: float) -> str:
        """Returns passed value as string formatting it based on numerical field type to be fractional or not."""
        return f"{int(value)}" if self.fractional == 0 else f"{value}"

    def bit_range_str(self) -> str:
        """Returns string representation of an inclusive offset range."""
        return f"[{self.end_offset()}:{self.offset}]"

    def __repr__(self):
        rw = "rw" if self.rw else "ro"
        return f"{self.name}@[{self.end_offset()}:{self.offset}]{self.signed}{self.width}.{self.fractional}#{rw}"

    def read_raw(self, data: BitArray) -> BitArray:
        """Returns a slice of input bit array corresponding to this field."""
        return data[(len(data) - self.end_offset() - 1) : (len(data) - self.offset)]

    def next_up_value(self, data: BitArray) -> float | int:
        """
        Given a complete register data return next valid larger value for this field or current value if
        it is already maximum allowed as per numeric type specification.
        """
        return self.__next(data, 1)

    def next_down_value(self, data: BitArray) -> float | int:
        """
        Given a complete register data return next valid smaller value for this field or current value if
        it is already minimum allowed as per numeric type specification.
        """
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
        """Given a complete register data bit array return value of this field as interpreted by its numerical type."""
        return self.__read_from_raw_field(self.read_raw(data))

    def write(self, data: BitArray, value: float) -> None:
        """
        Given a complete register data bit array write value into it interpreting it as per this field numeric type.
        Exception will be raised if provided value is outside of valid range of values for this field.
        """
        new_val = int(value * pow(2, self.fractional))
        tspec = ("int:" if self.signed == "S" else "uint:") + f"{self.width}={new_val}"
        data.overwrite(len(data) - self.end_offset() - 1, BitArray(tspec))

    @staticmethod
    def value_of(field_definition: str) -> "FieldDef":
        """
        Creates a FieldDef instance from user friendly string definition. Input string must be in the following format:
        ```

            <name>@<offset_range><numeric_type><rw_status>

            <name>             = $string([a-zA-Z_]+[0-9]*)
            <offset_range>     = [<end_offset>] | [<end_offset>:<start_offset>]
            <numeric_type>     = S<field_width_bits>.<fractional_bits> | U<field_width_bits>.<fractional_bits>
            <rw_status>        = "rw" | "rw" | none
            <end_offset>       = $positive_integer
            <start_offset>     = $positive_integer
            <field_width_bits> = $positive_integer
            <fractional_bits>  = $positive_integer
        ```

        Note that this does not allow you to provide field description or valid enum values. To that end use
        methods with_description(...) and with_enum(...).
        """
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
        """Adds description to this field."""
        self.desc = desc
        return self

    def with_enum(self, values: list[EnumValue]) -> Self:
        """Adds list of enum values to this field."""
        if len({v.name for v in values}) != len(values):
            raise ValueError("Duplicate name in enum values")
        if len({v.value for v in values}) != len(values):
            raise ValueError("Duplicate value in enum values")
        self.enum_values = values
        self.__validate__()
        return self


class Register:
    """
    This class encapsulates a register model and in-memory data store optionally linked to the external device.
    """

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
        reset: str | BitArray = "0x0",
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
            reset: bitarray value to which register will be reset; this is also the initial value which register will
                have before reading its value from the physical devices.
        """
        if name is not None and not Register.register_name_re.match(name):
            raise ValueError("Invalid register name.")

        if bit_len <= 0:
            raise ValueError("Register width must be greater than zero")

        reset_uint_value = BitArray(reset).uint if isinstance(reset, str) else reset.uint
        self.__reset_data = BitArray(f"uint:{bit_len}={reset_uint_value}")

        self.data: BitArray = self.__reset_data.copy()
        self._originial_data = self.__reset_data.copy()

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
    def reset_value(self) -> BitArray:
        """Returns reset value."""
        return self.__reset_data.copy()

    @property
    def desc(self):
        """Returns register description."""
        return self.__desc

    @desc.setter
    def desc(self, desc: str):
        self.__desc = desc

    @property
    def width(self) -> int:
        """Returns register width in bits."""
        return self.__width

    @width.setter
    def width(self, new_width: int):
        self.__validate_model_wrt_width(self._model, new_width)
        self.__width = new_width
        self._originial_data = BitArray.from_zeros(new_width)
        self.data = BitArray.from_zeros(new_width)

    def replace_model(self, new_model: list[FieldDef]) -> Self:
        """Replaces register field model with new one."""
        field_names: set[str] = {fd.name for fd in new_model}
        if len(field_names) != len(new_model):
            raise ValueError("Duplicate field names in the model")
        self.__validate_fields_overlapp(new_model)
        self.__validate_model_wrt_width(new_model, self.width)
        self._model.clear()
        self._model.extend(new_model)
        self._model.sort(key=lambda fd: -fd.offset)
        return self

    def copy(self) -> Self:
        """Returns a copy of the register."""
        register_copy = Register(
            bit_len=self.width,
            model=[fd.copy() for fd in self._model],
            address=self.address,
            name=self.name,
            link_provider=self.__link_provider,
            reset=self.reset_value,
        )
        register_copy.data = self.data.copy()
        register_copy._originial_data = self._originial_data.copy()
        return register_copy

    def is_changed(self) -> bool:
        """
        Returns True or False indicating of register data has changed since it was loaded. This method is only usefull
        when external storage is linked to the register and read() or write() methods are called.
        """
        return self._originial_data != self.data

    def pretty_print(self) -> str:
        """Returns human-readable register definition."""
        r = [{1: "Register:", 2: self.name}]
        if self.desc is not None and self.desc.strip() != "":
            r.append({1: "Description:", 2: self.desc})
        if self.address is not None:
            r.append({1: "Address:", 2: f"0x{self.address:X}"})
        r.append({1: "Width (bits):", 2: f"{self.width}"})
        r.append({1: "Reset data:", 2: f"0b{self.reset_value.bin}"})
        r.append({1: "Raw data:", 2: f"0b{self.data.bin}"})

        field_name_width = max([len(f.name) for f in self._model]) + 1
        field_range_width = max([len(f.bit_range_str()) for f in self._model]) + 1
        field_numtype_width = max([len(f.num_type()) for f in self._model]) + 1
        field_value_width = max([len(str(self.get_field_value(f.name))) for f in self._model]) + 1
        fields_table = ""
        for f in self._model:
            v = f.format(self.get_field_value(f.name))
            fields_table += (
                f.name.ljust(field_name_width)
                + f.bit_range_str().ljust(field_range_width)
                + f.num_type().ljust(field_numtype_width)
                + f.rw_mode()
                + " => "
                + v.ljust(field_value_width)
                + (f" # {f.desc}" if f.desc is not None else "")
                + "\n"
            )
            if f.enum_values is not None:
                enum_names_width = max(len(e.name) for e in f.enum_values) + 2
                enum_values_width = max(len(str(e.value)) for e in f.enum_values) + 2
                for e in f.enum_values:
                    fields_table += (
                        "    > "
                        + e.name.ljust(enum_names_width)
                        + f.format(e.value).ljust(enum_values_width)
                        + e.desc
                        + "\n"
                    )

        r.append({1: "Fields:", 2: fields_table})
        return tabulate(r, tablefmt="plain", missingval="")

    def __eq__(self, another: object) -> bool:
        if not isinstance(another, Register):
            return False
        else:
            return (
                self.name == another.name
                and self.address == another.address
                and self.address_bus_width_bytes == another.address_bus_width_bytes
                and self.desc == another.desc
                and self.width == another.width
                and self.reset_value == another.reset_value
                and self._model == another._model
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
            "reset": f"0b{self.reset_value.bin}",
            "fields": [dataclasses.asdict(field_def) for field_def in self._model],
        }

    def to_json_def(self, indent: int | None = None) -> str:
        """Exports register definition as json text."""
        return json.dumps(self.to_dict_def(), indent=2)

    @staticmethod
    def from_dict_def(data: dict) -> "Register":
        """Creates instance of he Register from dict."""
        fd_adapter = TypeAdapter(FieldDef)
        return Register(
            bit_len=data["width"],
            name=data["name"],
            desc=data["desc"] if "desc" in data else "",
            address=None if data["address"] is None else int(data["address"], 16),
            address_bus_width_bytes=data["address_bus_width_bytes"],
            model=[fd_adapter.validate_python(f) for f in data["fields"]],
            reset=data.get("reset", "0b0"),
        )

    @staticmethod
    def from_json_def(json_str: str) -> "Register":
        """Imports register definition from json text and returns instance of Register."""
        return Register.from_dict_def(json.loads(json_str))

    def set_field_value(self, field: str, value: float | str | EnumValue) -> float | int:
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
            elif isinstance(value, EnumValue):
                valid_enum_values = self.get_field_definition(field).enum_values
                if valid_enum_values is None or value not in valid_enum_values:
                    raise ValueError(f"Invalid enum value [{value}] for field {field}")
                else:
                    return value.value
            else:
                return value

        value = get_value()
        min, max = field_def.range()
        if min <= value <= max:
            field_def.write(self.data, value)
            return field_def.read(self.data)
        else:
            raise ValueError(f'Value {value} is out of range [{field_def.range()}] for field "{field}"')

    def get_field_enum_value(self, field: str) -> EnumValue | float | int:
        """
        Returns field value for a given field name as EnumValue if matching feild value is present in the field
        defintiion.

        """

    def get_field_value(self, field: str) -> float | int:
        """
        Returns field value for a given field. Returned value will be converted to int or float
        as defined in the fixed point format for this field.
        """
        field_def = self._fields_by_name.get(field)
        if field_def is None:
            raise ValueError(f'There is no field "{field}" in this register.')
        else:
            return field_def.read(self.data)

    def get_next_up_field_value(self, field: str) -> float | int:
        """
        Returns next field value that is larger than the current one for a given field. This is possible
        because numeric types for a field are always fixed point numbers which define finite discrete set
        of values. If current value for this field is the largest one, then current value is returned.
        """
        field_def = self._fields_by_name.get(field)
        if field_def is None:
            raise ValueError(f'There is no field "{field}" in this register.')
        else:
            return field_def.next_up_value(self.data)

    def get_next_down_field_value(self, field: str) -> float | int:
        """
        Returns next field value that is smaller than the current one for a given field. This is possible
        because numeric types for a field are always fixed point numbers which define finite discrete set
        of values. If current value for this field is the smallest one, then current value is returned.
        """
        field_def = self._fields_by_name.get(field)
        if field_def is None:
            raise ValueError(f'There is no field "{field}" in this register.')
        else:
            return field_def.next_down_value(self.data)

    def get_field_value_raw(self, field: str) -> BitArray:
        """Returns raw BitArray object for this field."""
        field_def = self._fields_by_name.get(field)
        if field_def is None:
            raise ValueError(f'There is no field "{field}" in this register.')
        else:
            return field_def.read_raw(self.data)

    def get_field_values(self) -> dict[str, float]:
        """Retruns dict of field name to value contained within each field."""
        return {m.name: self.get_field_value(m.name) for m in self._model}

    def get_field_definition(self, field: str) -> FieldDef:
        """Returns field definition (model spec) for a given field."""
        if field in self._fields_by_name:
            return self._fields_by_name[field]
        else:
            raise ValueError(f'There is no field "{field}" in this register.')

    @property
    def fields_defs_obj(self) -> object:
        return self.mk_field_model_accessor()

    def get_field_names(self) -> list[str]:
        """Returns list of field names present in this register."""
        return [m.name for m in self._model]

    def link(self, link: RLink, register_address: int | None = None) -> None:
        """
        Links register to external store. If optional address is provided, then it will be used to access external store
        even if register has address in its definition. If optional address is not provided, then address defined in the
        register will be used. If no addresses are given and present in the internal register definition then ValueError
        will be raised.

        Args:
            link: link to external store
            register_address: address of register in external store
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
        """Sets provider of the RLink."""
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

        Args:
            read_back: If True, then immediately after write operation read it back. If False, then do just write op.
            if_changed_only: If True, then check if register in memory model changed and if so then do write,
                otherwise do not write (return False). If False (default), then always write.

        Returns:
            True or False if write operation was successful or not.
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

    def mk_field_model_accessor(self) -> object:
        all_fields = "[" + ", ".join(self.get_field_names()) + "]"

        class FieldModelAccessor:
            def __repr__(self) -> str:
                return all_fields

        fma = FieldModelAccessor()
        for field_name in self.get_field_names():
            fma.__setattr__(field_name, self.__mk_embedding_field_enum_class(field_name))
        return fma

    def __mk_embedding_field_enum_class(self, field_name: str) -> object:
        field_def = self.get_field_definition(field_name)
        enums = field_def.enum_values

        def get_repr() -> str:

            rw = "rw" if field_def.rw else "ro"
            field_repr = (
                f"Field: {field_def.name}\n"
                f"  BitRange: [{field_def.end_offset()}:{field_def.offset}]\n"
                f"  NumType: {field_def.signed}{field_def.width}.{field_def.fractional}\n"
                f"  Access: {rw}\n"
            )
            if field_def.desc is not None and field_def.desc.strip() != "":
                field_repr += f"  Description: {field_def.desc}"
            if enums is not None:
                field_repr += "  Enum Values: [" + ", ".join([str(e) for e in enums]) + "]"
            return field_repr

        all_enums = get_repr()

        class FieldModelEnumAccessor:
            def __repr__(self) -> str:
                return all_enums

            def __call__(self, value: float | None = None):
                if value is None:
                    return enums
                elif enums is None:
                    return value
                else:
                    for e in enums:
                        if e.value == value:
                            return e
                    return None

        fma = FieldModelEnumAccessor()
        if enums is not None:
            for e in enums:
                fma.__setattr__(e.name, e)
        return fma

    def mk_embedding_class(self, link_provider: Callable[[], RLink], auto_sync: bool) -> object:
        register = self.copy()
        register.set_link_provider(link_provider)

        attrs = {
            "_read": register.read,
            "_write": register.write,
            "__repr__": register.__repr__,
            "__call__": lambda _: register.data,
            "__model__": register,
        }

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

        for field_name in self.get_field_names():
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
