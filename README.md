# RGSCore

[![License - MIT](https://img.shields.io/badge/License-MIT-blue)](https://github.com/Brainless-Software/rgscore/blob/master/LICENSE)
[![PyPI Latest Release](https://img.shields.io/pypi/v/rgscore.svg)](https://pypi.org/project/rgscore/)
[![pytest](https://github.com/Brainless-Software/rgscore/actions/workflows/test.yml/badge.svg)](https://github.com/Brainless-Software/rgscore/actions/workflows/test.yml)

Python library that provides classes for representing, defining and accessing registers on the embedded devices.

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
            model=[FieldDef.value_of("b1@[3:0]U4.1#ro"), FieldDef.value_of("b2@[5:4]S2.0#rw")],
        ),
    ]
)
```

To add this library to your project do

```shell
uv add rgscore
```

