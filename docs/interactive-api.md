## Interactive API

API described in the previous pages is more applicable to developers writing applications on top of this library. For
electrical engineers using this library there are two other API end points, `dut` (aka. Device Under Test)
and `regList`. The first one, `dut`, is for accessing live registers values, and second one, `regLsit`, holds minimal
necessary subset of register and fields definitions.

Consider an example of accessing
device [BMP581](https://www.bosch-sensortec.com/en/products/environmental-sensors/pressure-sensors/bmp581).
We assume that it is present on the I2C bus at address 0x47. For this chip we do have address map json file
at https://raw.githubusercontent.com/Brainless-Software/rgscore/refs/heads/master/devices/AddrMap_BMP581.json

```python
from i2c_drivers import I2CMasterI2CDriver

from rgscore import AddrMap, RLinkI2C, read, write

addrMap = AddrMap.new_instance_from_url(
    "https://raw.githubusercontent.com/Brainless-Software/rgscore/refs/heads/master/devices/AddrMap_BMP581.json",
    link=RLinkI2C(I2CMasterI2CDriver(), 0x47)
)

dut = addrMap.dut
regList = addrMap.regList
```

For `dut` (instance of `DeviceUnderTest` class) following rules apply:

1. `dut.$register_name` returns a register (instance of `HardwareRegister`)
2. `dut.$register_name.$field_name` returns value of a field in this register.
3. `dut.$register_name.$field_name = $number | EnumValue` assigns value to this field.
4. `read(dut.$register_name)` reads register value from the connected hardware device.
5. `write(dut.$register_name)` writes register value to the connected hardware device.

For `regList` (instance of `RegList` class) following rules apply:

1. `regList.$register_name` returns `FieldModelAccessor` class which in turn allows one to access fields.
2. `regList.$register_name.$field_name` return object to access associated enum values if any.
3. `regList.$register_name()` returns list of field names.
4. `regList.$register_name.$field_name()` returns list of enum values if any.
5. `regList.$register_name.$field_name($number)` returns associated enum value of `$number` matches any enum or just
   that number if no enums defined, otherwise `None`.
6. `print(regList.$register_name)` prints basic register model

The json file loaded above has entries for the following registers

```python
from rgscore import AddrMap, Register, EnumValue, FieldDef

Register(
    bit_len=8,
    address=0x7E,
    name="CMD",
    reset=0,
    model=[
        FieldDef.value_of("cmd@[7:0]U8.0#rw").with_enum([
            EnumValue("nvm_write_en", 0xA0), EnumValue("soft_reset", 0xB6)
        ])
    ]
)
```

We can then issue soft reset like so

```python
dut.CMD.cmd = regList.CMD.cmd.soft_reset  # set `cmd` field to 182 (soft_reset enum value) 
write(dut.CMD)  # write this register to the device.
time.sleep(0.002)  # reset takes 2 milliseconds
```

Note that you can also set `CMD.cmd` by simply supplying a number

```python
dut.CMD.cmd = 0xB6
```

Accessing `regList.CMD.cmd` returns object with all enum values. But calling `regList.CMD.cmd()` returns
list of all enums for this field.

```python
print(regList.CMD.cmd())
```

Prints

```shell
[nvm_write_en(160.0), soft_reset(182.0)]
```

And calling register returns list of field names

```python
print(regList.DRIVE_CONFIG())
```

Prints

```shell
['pad_if_drv', 'spi3_en', 'i2c_csb_pup_en']
```

while

```python
print(regList.DRIVE_CONFIG)
```

prints

```shell
Register: DRIVE_CONFIG
  Addr:      0x13
  Desc:      Configure host interface related settings (NVM-backed)
  Bit Width: 8
  Reset:     0b00110000
  Fields:    [pad_if_drv, spi3_en, i2c_csb_pup_en]
```