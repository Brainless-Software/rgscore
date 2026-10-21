import json
import re

import pytest
from bitstring import BitArray

from rgscore import FieldDef, Register, RegList
from rgscore.model.register import RLink


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


def test_json_serialization():
    rgsl = RegList(
        registers=[
            Register(
                bit_len=8,
                name="Moo",
                address=0x02,
                model=[
                    FieldDef.value_of("a@[3:0]U4.1#ro"),
                    FieldDef.value_of("b@[6:4]S3.0"),
                ],
            )
        ]
    )
    rgsl.add(
        Register(
            bit_len=8,
            name="Foo",
            address=0x01,
            model=[FieldDef.value_of("a@[3:0]U4.1#ro")],
        )
    )

    json_def = rgsl.to_json_def()

    rl = RegList.from_json_def(json_def)
    assert rl.to_json_def() == rgsl.to_json_def()


def test_delete_register():
    rgsl = RegList(
        registers=[
            Register(
                bit_len=8,
                name="Moo",
                address=0x02,
                model=[
                    FieldDef.value_of("a@[3:0]U4.1#ro"),
                    FieldDef.value_of("b@[6:4]S3.0"),
                ],
            ),
            Register(
                bit_len=8,
                name="Foo",
                address=0x01,
                model=[FieldDef.value_of("a@[3:0]U4.1#ro")],
            ),
            Register(
                bit_len=7,
                name="XYZ",
                address=0x05,
                model=[FieldDef.value_of("a@[3:0]U4.1#ro")],
            ),
        ]
    )
    assert [r.name for r in rgsl.registers] == ["Foo", "Moo", "XYZ"]
    rgsl.delete_register_by_name("Moo")
    assert [r.name for r in rgsl.registers] == ["Foo", "XYZ"]
    rgsl.add(
        Register(
            bit_len=11,
            name="Foo1",
            address=0x03,
            model=[FieldDef.value_of("abc@[3:0]U4.1#ro")],
        )
    )
    assert [r.name for r in rgsl.registers] == ["Foo", "Foo1", "XYZ"]
    rgsl.add(
        Register(
            bit_len=8,
            name="Moo",
            address=0x02,
            model=[
                FieldDef.value_of("a@[3:0]U4.1#ro"),
                FieldDef.value_of("b@[6:4]S3.0"),
            ],
        )
    )
    assert [r.name for r in rgsl.registers] == ["Foo", "Moo", "Foo1", "XYZ"]


def test_update_register():
    changes = []
    rgsl = RegList(on_change_callback=lambda rl: changes.append(len(changes)))
    assert changes == []
    rgsl.add(
        [
            Register(
                bit_len=8,
                name="Moo",
                address=0x02,
                model=[
                    FieldDef.value_of("a@[3:0]U4.1#ro"),
                    FieldDef.value_of("b@[6:4]S3.0"),
                ],
            ),
            Register(
                bit_len=8,
                name="Foo",
                address=0x01,
                model=[FieldDef.value_of("a@[3:0]U4.1#ro")],
            ),
            Register(
                bit_len=7,
                name="XYZ",
                address=0x05,
                model=[FieldDef.value_of("a@[3:0]U4.1#ro")],
            ),
        ]
    )

    # now there should be one change registered in the callback
    assert changes[-1] == 0

    assert [r.name for r in rgsl.registers] == ["Foo", "Moo", "XYZ"]
    register_moo_original = rgsl.get_register_by_name("Moo")
    assert register_moo_original is not None
    register_moo_copy = register_moo_original.copy()
    register_moo_copy.name = "MooA"
    register_moo_copy.address = 0x0A

    assert changes[-1] == 0  # no changes yet
    rgsl.update_register_def(register_moo_original, register_moo_copy)

    # now there should be one more change
    assert changes[-1] == 1

    assert [r.name for r in rgsl.registers] == ["Foo", "XYZ", "MooA"]

    register_foo_original = rgsl.get_register_by_name("Foo")
    assert register_foo_original is not None
    register_foo_copy = register_foo_original.copy()
    register_foo_copy.replace_model([FieldDef.value_of("z@[3:0]U4.1#ro"), FieldDef.value_of("x@[7:4]U4.1#rw")])

    rgsl.update_register_def(register_foo_original, register_foo_copy)
    # now there should be one more change
    assert changes[-1] == 2


def test_update_register_value_error_no_address():
    """Test ValueError when new_register has no address."""
    rgsl = RegList(
        registers=[
            Register(
                bit_len=8,
                name="Foo",
                address=0x01,
                model=[FieldDef.value_of("a@[3:0]U4.1#ro")],
            )
        ]
    )
    original = rgsl.get_register_by_name("Foo")
    assert original is not None
    new_reg = original.copy()
    new_reg.address = None  # type: ignore[assignment]

    with pytest.raises(ValueError, match="To be added Register must have an address"):
        rgsl.update_register_def(original, new_reg)


def test_update_register_value_error_no_name():
    """Test ValueError when new_register has no name."""
    rgsl = RegList(
        registers=[
            Register(
                bit_len=8,
                name="Foo",
                address=0x01,
                model=[FieldDef.value_of("a@[3:0]U4.1#ro")],
            )
        ]
    )
    original = rgsl.get_register_by_name("Foo")
    assert original is not None
    new_reg = original.copy()
    new_reg.name = None  # type: ignore[assignment]

    with pytest.raises(ValueError, match="To be added Register must have a name"):
        rgsl.update_register_def(original, new_reg)


def test_update_register_value_error_duplicate_name():
    """Test ValueError when new_register name conflicts with existing register."""
    rgsl = RegList(
        registers=[
            Register(
                bit_len=8,
                name="Foo",
                address=0x01,
                model=[FieldDef.value_of("a@[3:0]U4.1#ro")],
            ),
            Register(
                bit_len=8,
                name="Bar",
                address=0x02,
                model=[FieldDef.value_of("b@[3:0]U4.1#ro")],
            ),
        ]
    )
    original = rgsl.get_register_by_name("Foo")
    assert original is not None
    new_reg = original.copy()
    new_reg.name = "Bar"  # Conflict with existing register

    with pytest.raises(ValueError, match=re.escape("Register under a name [Bar] is already in the set")):
        rgsl.update_register_def(original, new_reg)


def test_update_register_value_error_duplicate_address():
    """Test ValueError when new_register address conflicts with existing register."""
    rgsl = RegList(
        registers=[
            Register(
                bit_len=8,
                name="Foo",
                address=0x01,
                model=[FieldDef.value_of("a@[3:0]U4.1#ro")],
            ),
            Register(
                bit_len=8,
                name="Bar",
                address=0x02,
                model=[FieldDef.value_of("b@[3:0]U4.1#ro")],
            ),
        ]
    )
    original = rgsl.get_register_by_name("Foo")
    assert original is not None
    new_reg = original.copy()
    new_reg.address = 0x02  # Conflict with existing register

    with pytest.raises(ValueError, match=re.escape("Register at this address [2] is already in the set")):
        rgsl.update_register_def(original, new_reg)


def test_update_register_same_name_allowed():
    """Test that keeping the same name is allowed."""
    rgsl = RegList(
        registers=[
            Register(
                bit_len=8,
                name="Foo",
                address=0x01,
                model=[FieldDef.value_of("a@[3:0]U4.1#ro")],
            )
        ]
    )
    original = rgsl.get_register_by_name("Foo")
    assert original is not None
    new_reg = original.copy()
    new_reg.address = 0x03  # Change address, keep same name

    rgsl.update_register_def(original, new_reg)
    assert rgsl.get_register_by_name("Foo") is not None
    assert rgsl.get_register_by_name("Foo").address == 0x03


def test_update_register_same_address_allowed():
    """Test that keeping the same address is allowed."""
    rgsl = RegList(
        registers=[
            Register(
                bit_len=8,
                name="Foo",
                address=0x01,
                model=[FieldDef.value_of("a@[3:0]U4.1#ro")],
            )
        ]
    )
    original = rgsl.get_register_by_name("Foo")
    assert original is not None
    new_reg = original.copy()
    new_reg.name = "Bar"  # Change name, keep same address

    rgsl.update_register_def(original, new_reg)
    assert rgsl.get_register_by_name("Bar") is not None
    assert rgsl.get_register_by_name("Bar").address == 0x01


def test_add_empty_list():
    """Test that adding an empty list is a no-op."""
    rgsl = RegList()
    rgsl.add([])
    assert rgsl.registers == []


def test_add_register_no_address():
    """Test ValueError when adding a register without an address."""
    rgsl = RegList()
    reg = Register(bit_len=8, name="Foo", model=[FieldDef.value_of("a@[3:0]U4.1")])
    with pytest.raises(ValueError, match="To be added Register must have an address"):
        rgsl.add(reg)


def test_add_register_implicit_name():
    """Test that implicit name is created when register has no name."""
    rgsl = RegList()
    reg = Register(bit_len=8, address=0x10, model=[FieldDef.value_of("a@[3:0]U4.1")])
    # No name provided
    assert reg.name is None

    rgsl.add(reg)
    # Name should be auto-generated as "R{address}"
    assert reg.name == "R16"
    assert rgsl.get_register_by_name("R16") is reg


def test_add_register_duplicate_name():
    """Test ValueError when adding a register with duplicate name."""
    rgsl = RegList(
        registers=[
            Register(
                bit_len=8,
                name="Foo",
                address=0x01,
                model=[FieldDef.value_of("a@[3:0]U4.1")],
            )
        ]
    )
    reg2 = Register(
        bit_len=8,
        name="Foo",  # Same name
        address=0x02,
        model=[FieldDef.value_of("b@[3:0]U4.1")],
    )

    with pytest.raises(ValueError, match=re.escape("Register under a name [Foo] is already in the set")):
        rgsl.add(reg2)


def test_add_register_duplicate_address():
    """Test ValueError when adding a register with duplicate address."""
    rgsl = RegList(
        registers=[
            Register(
                bit_len=8,
                name="Foo",
                address=0x01,
                model=[FieldDef.value_of("a@[3:0]U4.1")],
            )
        ]
    )
    reg2 = Register(
        bit_len=8,
        name="Bar",
        address=0x01,  # Same address
        model=[FieldDef.value_of("b@[3:0]U4.1")],
    )

    with pytest.raises(ValueError, match=re.escape("Register at this address [0x0001] is already in the set")):
        rgsl.add(reg2)


def test_add_register_with_store_link():
    """Test that registers are linked to store when store is provided."""
    store = MemLink()
    rgsl = RegList(store=store)
    reg = Register(
        bit_len=8,
        name="Foo",
        address=0x0A,
        model=[FieldDef.value_of("a@[3:0]U4.1")],
    )

    rgsl.add(reg)
    # Register should be linked to the store
    assert reg.linked_address == 0x0A
    # Verify read works (store has value at 0xA)
    reg.read()
    assert reg.get_field_value("a") == 1.5


def test_get_register_by_address():
    """Test getting register by address."""
    rgsl = RegList(
        registers=[
            Register(
                bit_len=8,
                name="Foo",
                address=0x01,
                model=[FieldDef.value_of("a@[3:0]U4.1")],
            ),
            Register(
                bit_len=8,
                name="Bar",
                address=0x02,
                model=[FieldDef.value_of("b@[3:0]U4.1")],
            ),
        ]
    )

    reg = rgsl.get_register_by_address(0x02)
    assert reg is not None
    assert reg.name == "Bar"

    # Non-existent address
    assert rgsl.get_register_by_address(0x99) is None


def test_read_all():
    """Test reading all registers from linked store."""
    store = MemLink()
    rgsl = RegList(store=store)
    reg1 = Register(
        bit_len=8,
        name="Foo",
        address=0x0A,
        model=[FieldDef.value_of("a@[3:0]U4.1")],
    )
    reg2 = Register(
        bit_len=16,
        name="Bar",
        address=0x09,
        model=[FieldDef.value_of("b@[15:0]U16.0")],
    )
    rgsl.add([reg1, reg2])

    # Initially registers have default values (0)
    assert reg1.get_field_value("a") == 0.0
    assert reg2.get_field_value("b") == 0.0

    # Read all should populate registers from store
    rgsl.read_all()

    # Store has 0xA -> uint:8=3 (so a=3*2^0.1 = 3*1.25 = 3.75? wait, field is U4.1 at bits 3:0)
    # Actually 0x03 = 00000011, lower 4 bits are 0011 = 3, so U4.1 = 3/2 = 1.5
    assert reg1.get_field_value("a") == 1.5
    # Store has 0x9 -> uint:16=7
    assert reg2.get_field_value("b") == 7.0


def test_write_all():
    """Test writing all registers to linked store."""
    store = MemLink()
    rgsl = RegList(store=store)
    reg1 = Register(
        bit_len=8,
        name="Foo",
        address=0x0A,
        model=[FieldDef.value_of("a@[3:0]U4.1")],
    )
    reg2 = Register(
        bit_len=8,
        name="Bar",
        address=0x08,  # Not in store, write should silently fail
        model=[FieldDef.value_of("b@[3:0]U4.1")],
    )
    rgsl.add([reg1, reg2])

    # Modify register values
    reg1.set_field_value("a", 2.5)  # 2.5 * 2 = 5 = 0101 in lower 4 bits
    reg2.set_field_value("b", 3.0)

    # Write all
    rgsl.write_all()

    # Verify store was updated for reg1 (0x0A)
    assert store.store[0x0A] == BitArray("uint:8=5")

    # reg2 (0x08) not in store, so write should have failed silently (no exception)
    assert 0x08 not in store.store.keys()


def test_load_from_json_def_invalid_class():
    """Test ValueError when JSON class is not RegList."""
    rgsl = RegList()
    invalid_json = json.dumps({"class": "NotRegList", "version": 1, "registers": []})

    with pytest.raises(ValueError, match="Provided json document does not represent regList"):
        rgsl.load_from_json_def(invalid_json)


def test_load_from_json_def_unsupported_version():
    """Test ValueError when JSON version is not supported."""
    rgsl = RegList()
    invalid_json = json.dumps({"class": "RegList", "version": 200, "registers": []})

    with pytest.raises(ValueError, match="Provided regList json has unsupported version 200"):
        rgsl.load_from_json_def(invalid_json)
