import re

import pytest

from rgscore import FieldDef, Register, RegList


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
