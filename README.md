# RGSCore

[![License - MIT](https://img.shields.io/badge/License-MIT-blue)](https://github.com/Brainless-Software/rgscore/blob/master/LICENSE)
[![PyPI Latest Release](https://img.shields.io/pypi/v/rgscore.svg)](https://pypi.org/project/rgscore/)
[![pytest](https://github.com/Brainless-Software/rgscore/actions/workflows/test.yml/badge.svg)](https://github.com/Brainless-Software/rgscore/actions/workflows/test.yml)
[![Documentation](https://img.shields.io/badge/docs-latest-brightgreen)](https://brainless-software.github.io/rgscore/)

Python library that provides classes for representing, defining and accessing registers in the embedded devices.

To add this library to your project do

```shell
uv add rgscore
```

## Library purpose

1. To provide python API to define registers and serialize it into persistent json store/file.
2. To provide access from Python to serialized form of register definitions (aka. regList json).
3. Together with other libraries, such as [i2c-api](https://brainless-software.github.io/i2c_api/)
   and [i2c-drivers](https://github.com/Brainless-Software/i2c_drivers), to provide read and write access from Python to
   registers
   in live devices.

## Overall structure

To fulfill above goals this library defines following classes

* `Register` - defines/holds name, address, description, in-memory bitarray storage, reset value
  and a model of fields (list of `FieldDef` objects).
* `FieldDef` - holds register field definition which includes field name, bit-range in the larger
  register bitarray, numeric type, r/w flag, description and optional enum values that maps numeric
  value held in a register field to symbolic names.
* `EnumValue` - symbolic name corresponding to a numeric value in the field. Also includes description.
* `RLink` - abstract class that connects registers to physical hardware. Requires implementation that drives
  low level communication to live device.
* `RLinkI2C` - implementation of `RLink` suitable for linking classes in this library to physical devices
  over I2C bus.
* `RegList` - grouping of registers ensuring their uniqueness within regList. Primary class for (de)serialization
  to/from json file.

## Defining registers programmatically

Registers are grouped into ordered collections known as regList's, represented by `RegList` class. When registers are
added to the regList

Example:

```python
from rgscore import Register, RegList, FieldDef

reglist = RegList(
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
            desc="Very important register",
            model=[FieldDef.value_of("b1@[3:0]U4.1#ro"), FieldDef.value_of("b2@[5:4]S2.0#rw")],
        ),
    ]
)
```

## Loading regList from json file

## Accessing registers on physical devices

