import json

import pytest
from bitstring import BitArray

from rgscore.model.register import EnumValue, Field, FieldDef, Register, RLink


class MemLink(RLink):
    def __init__(self):
        self.store = {0x9: BitArray("uint:16=7"), 0xA: BitArray("uint:8=3")}
        self.__last_used_address_bus_width = [0]

    def last_used_address_bus_width(self) -> int:
        return self.__last_used_address_bus_width[0]

    def read(self, addr: int, address_bus_width: int, value_width: int) -> BitArray | None:
        self.__last_used_address_bus_width[0] = address_bus_width
        raw_register = self.store.get(addr)
        return None if raw_register is None else raw_register.copy()

    def write(self, addr: int, address_bus_width: int, value: BitArray) -> bool:
        self.__last_used_address_bus_width[0] = address_bus_width
        if addr in self.store:
            self.store[addr] = value.copy()
            return True
        else:
            return False


def test_bare_register_valid():
    # create 7 bits wide register with no explicit fields defined, no name and no address.
    r = Register(7)
    assert r.width == 7
    assert r.name is None
    assert r.address is None

    # implicit field named "val" is created occupying the whole of the register of type U{r.width}.0
    assert r.get_field_names() == ["val"]
    assert r.get_field_definition("val") == FieldDef(name="val", offset=0, signed="U", width=7, fractional=0, rw=True)


def test_bare_register_invalid():
    # register with must be greater than 0
    with pytest.raises(ValueError):
        Register(0)

    with pytest.raises(ValueError):
        Register(-4)


def test_register_with_name():
    r = Register(7, name="Foo1")
    assert r.name == "Foo1"

    # check that error is raised if name is invalid
    with pytest.raises(ValueError):
        Register(7, name="Foo X")

    with pytest.raises(ValueError):
        Register(7, name="1")


def test_register_with_address():
    r = Register(7, address=0x42)
    assert r.address == 0x42


def test_register_with_valid_fields():
    # define register with just one r/o field.
    r = Register(7, address=0x42, name="AReg", model=[FieldDef.value_of("a@[3:0]U4.1#ro")])
    assert r.get_field_names() == ["a"]


def test_register_with_invalid_fields():
    # field width is larger than register width
    with pytest.raises(ValueError):
        Register(7, address=0x42, name="AReg", model=[FieldDef.value_of("a@[7:0]U8.1")])

    # fields overlap
    with pytest.raises(ValueError):
        Register(
            bit_len=7,
            address=0x42,
            name="AReg",
            model=[FieldDef.value_of("a@[6:0]U7.1"), FieldDef.value_of("b@[3:2]S2.0")],
        )

    # fields names not unique
    with pytest.raises(ValueError):
        Register(
            bit_len=7,
            address=0x42,
            name="AReg",
            model=[FieldDef.value_of("a@[3:0]U4.1"), FieldDef.value_of("a@[6:4]S3.0")],
        )


def test_register_access():
    r = Register(
        bit_len=7,
        address=0x42,
        name="AReg",
        model=[
            FieldDef.value_of("a@[3:0]U4.1#ro"),
            FieldDef.value_of("b@[6:4]S3.0").with_enum([EnumValue("On", 1), EnumValue("Off", 0)]),
        ],
    )
    assert r.get_field_names() == ["b", "a"]
    assert r.get_field_values() == {"a": 0.0, "b": 0.0}
    assert r.get_field_value("a") == 0.0

    # error on non-existent field
    with pytest.raises(ValueError):
        r.get_field_value("x")

    # error on non-existent field
    with pytest.raises(ValueError):
        r.set_field_value("x", 1)

    r.set_field_value("b", 3)
    assert r.get_field_values() == {"a": 0.0, "b": 3.0}
    assert r.get_field_value("a") == 0.0
    assert r.get_field_value("b") == 3.0
    assert r.data.bin == "0110000"

    # error when trying to change r/o field
    with pytest.raises(ValueError):
        r.set_field_value("a", 1)

    # error when trying to set value outside valid range
    with pytest.raises(ValueError):
        r.set_field_value("b", 10)
    assert r.get_field_value("b") == 3.0

    # error when trying to set value outside valid range
    with pytest.raises(ValueError):
        r.set_field_value("b", -10)
    assert r.get_field_value("b") == 3.0

    r.set_field_value("b", -1)
    assert r.get_field_value("b") == -1.0

    # let us change field "a" to be r/w and check field valid range which is from 0 to +7.5 inclusive
    r = Register(
        bit_len=7,
        address=0x42,
        name="AReg",
        model=[
            FieldDef.value_of("a@[3:0]U4.1"),
            FieldDef.value_of("b@[6:4]S3.0").with_enum([EnumValue("On", 1), EnumValue("Off", 0)]),
        ],
    )

    assert r.set_field_value("a", 7.5) == 7.5
    assert r.get_field_value("a") == 7.5

    # following will truncate to lower bound
    assert r.set_field_value("a", 6.999) == 6.5
    assert r.get_field_value("a") == 6.5

    r.set_field_value("a", 0)
    assert r.get_field_value("a") == 0.0

    # setting outside valid range should fail
    with pytest.raises(ValueError):
        r.set_field_value("a", -0.1)

    with pytest.raises(ValueError):
        r.set_field_value("a", 7.5001)

    # set values from enum
    assert r.get_field_value("b") == 0.0
    r.set_field_value("b", "On")
    assert r.get_field_value("b") == 1.0
    assert r.get_field_value("b") == 1.0
    assert r.get_field_definition("b").valid_value_values[r.get_field_value("b")].name == "On"

    # invalid enum should raise ValueError
    with pytest.raises(ValueError):
        r.set_field_value("b", "Zzz")


def test_field_def():
    # fully written out valid field definition
    fd = FieldDef.value_of("a@[10:3]U8.3#ro")
    assert fd.name == "a"
    assert fd.width == 8
    assert fd.offset == 3
    assert fd.signed == "U"
    assert fd.fractional == 3
    assert not fd.rw

    # omitting rw flag implies "rw"
    fd = FieldDef.value_of("a@[10:3]U8.3")
    assert fd.name == "a"
    assert fd.width == 8
    assert fd.offset == 3
    assert fd.signed == "U"
    assert fd.fractional == 3
    assert fd.rw

    # field with width of 1 bit can be written as [offset] or [offset:offset]
    fd = (
        FieldDef.value_of("a@[5:5]U1.0")
        .with_description("Aloha")
        .with_enum([EnumValue("Yes", 1, "Do it"), EnumValue("No", 0, "Do not")])
    )
    assert fd.offset == 5
    assert fd.width == 1
    assert fd.desc == "Aloha"
    assert fd.enum_values == [EnumValue("Yes", 1, "Do it"), EnumValue("No", 0, "Do not")]

    # check duplicate enum values
    with pytest.raises(ValueError):
        FieldDef.value_of("a@[5:5]U1.0").with_enum([EnumValue("Yes", 1, "Do it"), EnumValue("No", 1, "Do not")])

    with pytest.raises(ValueError):
        FieldDef(
            name="a",
            offset=0,
            signed="U",
            width=2,
            fractional=0,
            rw=True,
            enum_values=[EnumValue("Yes", 1, "Do it"), EnumValue("No", 1, "Do not")],
        )

    with pytest.raises(ValueError):
        FieldDef.value_of("a@[5:5]U1.0").with_enum([EnumValue("Yes", 1, "Do it"), EnumValue("Yes", 0, "Do not")])

    with pytest.raises(ValueError):
        FieldDef(
            name="a",
            offset=0,
            signed="U",
            width=2,
            fractional=0,
            rw=True,
            enum_values=[EnumValue("Yes", 1, "Do it"), EnumValue("Yes", 0, "Do not")],
        )

    fd = FieldDef.value_of("a@[5]U1.0")
    assert fd.offset == 5
    assert fd.width == 1

    # field range [10:3] is of width 8 bits while numeric type is declared as unsigned 3 bits wide int. This is
    # internally inconsistent and should give rise to ValueError
    with pytest.raises(ValueError):
        FieldDef.value_of("a@[10:3]U3.0")

    # check for various invalid/incomplete field definitions
    with pytest.raises(ValueError):  # missing field name
        FieldDef.value_of("@[10:3]U3.1")

    with pytest.raises(ValueError):  # missing numeric name
        FieldDef.value_of("x@[10:3]")

    with pytest.raises(ValueError):  # missing bit range
        FieldDef.value_of("x@S3.0")

    f1 = (
        FieldDef.value_of("a@[3:0]U4.1#ro")
        .with_description("Aloha")
        .with_enum([EnumValue("X", 1, "xval"), EnumValue("Y", 2, "yval")])
    )
    f2 = f1.copy()
    f2.with_description("Hello").with_enum([EnumValue("Z", 4, "xval"), EnumValue("Y", 3, "yval")])
    assert f1.desc == "Aloha"
    assert f2.desc == "Hello"
    assert f1.enum_values == [EnumValue("X", 1, "xval"), EnumValue("Y", 2, "yval")]
    assert f2.enum_values == [EnumValue("Z", 4, "xval"), EnumValue("Y", 3, "yval")]

    f3 = Field(
        name="a",
        offset=0,
        numeric_type="U4.1",
        rw="ro",
        desc="Aloha",
        values=[EnumValue("X", 1, "xval"), EnumValue("Y", 2, "yval")],
    )
    assert f1 == f3
    assert f2 != f3

    with pytest.raises(ValueError):
        Field(name="a", offset=0, numeric_type="Z4.1")

    with pytest.raises(ValueError):
        Field(name="a", offset=0, numeric_type="U4.1", rw="rz")


def test_fielddef_validate_invalid_signed():
    """Test FieldDef.__validate__ raises ValueError for invalid signed value."""
    with pytest.raises(ValueError, match="Invalid signed value"):
        FieldDef(name="a", offset=0, signed="X", width=4, fractional=0, rw=True)


def test_fielddef_validate_negative_offset():
    """Test FieldDef.__validate__ raises ValueError for negative offset."""
    with pytest.raises(ValueError, match="Field offset must be a positive integer"):
        FieldDef(name="a", offset=-1, signed="U", width=4, fractional=0, rw=True)


def test_fielddef_format_fractional_zero():
    """Test FieldDef.format with fractional == 0 returns int string."""
    fd = FieldDef(name="a", offset=0, signed="U", width=4, fractional=0, rw=True)
    # fractional == 0 should return int string
    assert fd.format(3.0) == "3"
    assert fd.format(3.5) == "3"  # int(3.5) == 3


def test_fielddef_repr():
    """Test FieldDef.__repr__ method."""
    fd = FieldDef(name="test_field", offset=2, signed="U", width=4, fractional=1, rw=True)
    repr_str = repr(fd)
    assert "test_field" in repr_str
    assert "U4.1" in repr_str
    assert "#rw" in repr_str

    # Test read-only
    fd_ro = FieldDef(name="ro_field", offset=0, signed="S", width=3, fractional=0, rw=False)
    repr_str_ro = repr(fd_ro)
    assert "ro_field" in repr_str_ro
    assert "S3.0" in repr_str_ro
    assert "#ro" in repr_str_ro


def test_fielddef_next_up_value():
    """Test FieldDef.next_up_value method."""
    from bitstring import BitArray

    # Unsigned field
    fd = FieldDef(name="a", offset=0, signed="U", width=4, fractional=0, rw=True)
    data = BitArray("uint:4=5")
    # next_up_value should return 6
    assert fd.next_up_value(data) == 6

    # Signed field
    fd_signed = FieldDef(name="b", offset=0, signed="S", width=4, fractional=0, rw=True)
    data_signed = BitArray("int:4=2")
    assert fd_signed.next_up_value(data_signed) == 3


def test_fielddef_next_down_value():
    """Test FieldDef.next_down_value method."""
    from bitstring import BitArray

    # Unsigned field
    fd = FieldDef(name="a", offset=0, signed="U", width=4, fractional=0, rw=True)
    data = BitArray("uint:4=5")
    # next_down_value should return 4
    assert fd.next_down_value(data) == 4

    # Signed field
    fd_signed = FieldDef(name="b", offset=0, signed="S", width=4, fractional=0, rw=True)
    data_signed = BitArray("int:4=-2")
    assert fd_signed.next_down_value(data_signed) == -3


def test_fielddef_get_next_raw_field_out_of_range():
    """Test FieldDef.__get_next_raw_field when next value is out of range (ValueError caught)."""
    from bitstring import BitArray

    # Unsigned field at max value - next up should wrap/return same
    fd = FieldDef(name="a", offset=0, signed="U", width=4, fractional=0, rw=True)
    data = BitArray("uint:4=15")  # max value for 4 bits unsigned
    # next_up_value should return same value (15) since 16 is out of range
    assert fd.next_up_value(data) == 15

    # Signed field at max value
    fd_signed = FieldDef(name="b", offset=0, signed="S", width=4, fractional=0, rw=True)
    data_signed = BitArray("int:4=7")  # max value for 4 bits signed
    assert fd_signed.next_up_value(data_signed) == 7

    # Signed field at min value
    data_signed_min = BitArray("int:4=-8")  # min value for 4 bits signed
    assert fd_signed.next_down_value(data_signed_min) == -8


def test_fielddef_value_of_invalid_definition():
    """Test FieldDef.value_of raises ValueError for invalid field definition string."""
    with pytest.raises(ValueError, match="Invalid register field definition"):
        FieldDef.value_of("invalid_definition_string")

    # Test various invalid formats
    with pytest.raises(ValueError):
        FieldDef.value_of("")  # empty string

    with pytest.raises(ValueError):
        FieldDef.value_of("no_at_sign")

    with pytest.raises(ValueError):
        FieldDef.value_of("name@[3:0]")  # missing numeric type

    with pytest.raises(ValueError):
        FieldDef.value_of("name@[3:0]X4.0")  # invalid signed


def test_fielddef_with_enum_duplicate_name():
    """Test FieldDef.with_enum raises ValueError for duplicate enum names."""
    fd = FieldDef.value_of("a@[3:0]U4.0")
    with pytest.raises(ValueError, match="Duplicate name in enum values"):
        fd.with_enum([EnumValue("Same", 1), EnumValue("Same", 2)])


def test_fielddef_with_enum_duplicate_value():
    """Test FieldDef.with_enum raises ValueError for duplicate enum values."""
    fd = FieldDef.value_of("a@[3:0]U4.0")
    with pytest.raises(ValueError, match="Duplicate value in enum values"):
        fd.with_enum([EnumValue("A", 1), EnumValue("B", 1)])


def test_enumvalue_repr():
    """Test EnumValue.__repr__ method."""
    ev = EnumValue(name="TestEnum", value=42, desc="A test enum")
    repr_str = repr(ev)
    assert "42.0" in repr_str  # value is converted to float
    assert "TestEnum" in repr_str
    assert "A test enum" in repr_str

    # Test with empty description
    ev2 = EnumValue(name="Simple", value=1)
    repr_str2 = repr(ev2)
    assert "1.0" in repr_str2
    assert "Simple" in repr_str2
    assert "# " in repr_str2  # empty desc still shows "# "


def test_link():
    store = MemLink()
    r = Register(
        bit_len=8,
        address=0xA,
        name="AReg",
        model=[FieldDef.value_of("a@[3:0]U4.1"), FieldDef.value_of("b@[6:4]S3.0")],
    )
    # register is not linked yet, hence, r.write() should fail returning False
    assert r.write() == False
    assert store.last_used_address_bus_width() == 0

    assert r.is_changed() == False
    r.link(store)
    assert r.get_field_value("a") == 0.0
    r.read()
    assert store.last_used_address_bus_width() == 1
    assert r.is_changed() == False
    assert r.get_field_value("a") == 1.5

    # by default writing back just loaded value should happen
    assert r.write() == True

    # but writing back with if_changed_only set to True should not happen since we have not changed anything
    # in the register yet.
    assert r.write(if_changed_only=True) == False

    r.set_field_value("a", 0.5)
    assert r.is_changed() == True
    # calling read() should reset register value
    r.read()
    assert r.is_changed() == False
    assert r.get_field_value("a") == 1.5

    # now change register and write it to the store
    r.set_field_value("a", 0.5)
    assert r.get_field_value("a") == 0.5
    assert store.store[0xA] == BitArray("uint:8=3")
    assert r.write() == True
    assert r.is_changed() == False
    assert store.store[0xA] == BitArray("uint:8=1")

    # if register does not have an address and r.link(...) is missing address then error should be raised
    r = Register(8)
    with pytest.raises(ValueError):
        r.link(store)

    # but if address is provided than it is Ok
    r.link(store, 0xA)
    r.read()
    assert r.get_field_value("val") == 1.0

    # if register address is invalid then error "There is no register at the address ..." should be raised
    r.link(store, 0xB)
    with pytest.raises(RuntimeError):
        r.read()

    # check that bus_width in Register is correctly used in link
    r = Register(
        bit_len=8,
        address=0xA,
        address_bus_width_bytes=4,
        name="BReg",
        model=[FieldDef.value_of("a@[3:0]U4.1"), FieldDef.value_of("b@[6:4]S3.0")],
        link_provider=lambda: store,
    )
    r.write()
    assert store.last_used_address_bus_width() == 4


def test_json_serialization():
    r1 = Register(
        bit_len=8,
        name="Foo",
        address=0x01,
        address_bus_width_bytes=2,
        desc="Register_r1",
        model=[
            FieldDef.value_of("a@[3:0]U4.1#ro").with_description("A field").with_enum([EnumValue("A", 3, "a value")]),
            FieldDef.value_of("b@[6:4]S3.0"),
        ],
    )
    r_json = r1.to_json_def()
    data = json.loads(r_json)
    assert data["name"] == "Foo"
    assert data["address"] == "0x1"
    assert data["width"] == 8
    assert len(data["fields"]) == 2

    # now create new instance of Register from the json string
    r2 = Register.from_json_def(r_json)
    assert r2.name == "Foo"
    assert r2.address == 1
    assert r2.address_bus_width_bytes == 2
    assert r2.width == 8
    assert r2.get_field_names() == [
        "b",
        "a",
    ]  # fields are resorted by decreasing offset
    assert r_json == r2.to_json_def()


def test_register_fields_order():
    # field should be sorted in order of decreasing offsets
    register = Register(
        bit_len=8,
        name="Foo",
        address=0x01,
        model=[FieldDef.value_of("a@[3:0]U4.1#ro"), FieldDef.value_of("b@[6:4]S3.0")],
    )
    assert register.get_field_names() == ["b", "a"]


def test_register_copy():
    store = MemLink()
    r = Register(bit_len=8, name="AReg", link_provider=lambda: store, address=0xA)
    r.set_field_value("val", 3)
    r_copy = r.copy()
    r.set_field_value("val", 4)
    assert r_copy.to_json_def() == r.to_json_def()
    assert r_copy.get_field_value("val") == 3
    assert r.get_field_value("val") == 4


def test_register_change_def():
    r = Register(bit_len=8, name="AReg", address=0xA)
    r.set_field_value("val", 3)
    r.name = "BReg"
    r.address = 0xB
    assert r.get_field_value("val") == 3

    # narrowing width should fail since we have an implicit field that U8.0
    with pytest.raises(ValueError):
        r.width = 7

    # widening should work though and it should reset all values
    r.width = 10
    assert r.get_field_value("val") == 0

    r.replace_model([FieldDef.value_of("b@[3:0]U4.1#ro"), FieldDef.value_of("a@[6:4]S3.0")])
    # notice that order of fields is changed as they are sorted in order of decreasing offsets
    assert r.get_field_names() == ["a", "b"]

    # setting fields to extend outside of register width should fail
    with pytest.raises(ValueError, match='Field "b" extends outside of register width.'):
        r.replace_model([FieldDef.value_of("a@[3:0]U4.1#ro"), FieldDef.value_of("b@[16:14]S3.0")])


def test_embedding_class():
    store = MemLink()
    r = Register(
        bit_len=8,
        name="AReg",
        address=0xA,
        model=[FieldDef.value_of("a@[3:0]U4.1#rw"), FieldDef.value_of("b_raw@[6:4]S3.0")],
    )
    c = r.mk_embedding_class(lambda: store, auto_sync=False)
    rr = c()

    # embedding register class is callable, and it is returns underlining bitarray
    assert rr() == BitArray("0b00000000")

    assert rr.a == 0
    assert rr.a_raw == BitArray("0b0000")
    rr._read()
    assert rr.a == 1.5
    rr.a = 0
    assert rr.a == 0
    rr._read()
    assert rr.a == 1.5
    assert rr.a_raw == BitArray("0b0011")

    rr.a = 0
    rr._write()
    rr._read()
    assert rr.a == 0

    # check disambiguation of b_raw and b_raw_raw
    assert rr.b_raw == 0
    assert rr.b_raw_raw == BitArray("0b000")
