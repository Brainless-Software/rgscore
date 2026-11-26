# RGSCore - Complete LLM Reference Guide

## Overview

**RGSCore** is a Python library for representing, defining, and accessing hardware registers in embedded devices. It provides a type-safe, declarative API for register modeling with support for serialization, hardware communication, and interactive development.

### Key Features

1. **Register Modeling** - Define registers with fields, bit ranges, numeric types (fixed-point, BCD), enums, and access modes
2. **Serialization** - Full JSON (de)serialization with schema validation
3. **Hardware Access** - Abstract `RLink` interface with `RLinkI2C` implementation for I2C devices
4. **Interactive API** - `dut` (Device Under Test) and `regList` for REPL/jupyter usage
5. **Address Maps** - Collections of registers with uniqueness guarantees
6. **Remote Loading** - Load address maps from files or URLs with caching

### Installation

```bash
uv add rgscore
# or
pip install rgscore
```

**Dependencies**: `bitstring`, `i2c-api`, `pydantic`, `requests`, `tabulate`

**Python**: >= 3.13

---

## Core Concepts

### Numeric Types

| Type | Format | Description |
|------|--------|-------------|
| **Fixed-Point** | `U<width>.<frac>` or `S<width>.<frac>` | Unsigned/Signed fixed-point (Q format) |
| **BCD** | `BCD` | Binary Coded Decimal |

Examples:
- `U8.0` - 8-bit unsigned integer
- `S4.2` - 4-bit signed with 2 fractional bits (range -2.0 to +1.75)
- `U16.8` - 16-bit unsigned with 8 fractional bits
- `BCD` - Binary Coded Decimal (width must be specified separately)

### Field Definition String Format

```
<name>@[<end_offset>:<start_offset>]<num_type>#<rw_flag>
```

Or for single-bit fields:
```
<name>@[<offset>]<num_type>#<rw_flag>
```

Components:
- `<name>` - Valid Python identifier (`[a-zA-Z_][a-zA-Z0-9_]*`)
- `<end_offset>:<start_offset>` - Inclusive bit range (MSB:LSB), or just `[offset]` for 1-bit
- `<num_type>` - `U<w>.<f>`, `S<w>.<f>`, or `BCD`
- `#<rw_flag>` - Optional: `rw` (default) or `ro`

Examples:
```
"cmd@[7:0]U8.0#rw"      # 8-bit field at bits 7-0, unsigned int, read-write
"status@[3:0]U4.0#ro"   # 4-bit field at bits 3-0, read-only
"temp@[15:0]S16.8"      # 16-bit signed fixed-point with 8 fractional bits
"bcd_val@[7:0]BCD"      # 8-bit BCD field (width=8, 2 digits)
"flag@[5]U1.0#ro"       # Single bit at position 5
```

---

## API Reference

### Main Exports

```python
from rgscore import (
    AddrMap,              # Address map container
    Register,             # Register definition + data
    FieldDef,             # Field definition
    EnumValue,            # Enum value with name/value/desc
    BinaryCodedDecimal,   # BCD numeric type
    FixedPointNumber,     # Fixed-point numeric type
    Device,               # Device identification
    DeviceUnderTest,      # Interactive hardware access (via AddrMap.dut)
    RegList,              # Interactive model access (via AddrMap.regList)
    RLink,                # Abstract hardware link
    RLinkI2C,             # I2C hardware link
    S, U,                 # Fixed-point combinators for multi-register values
    read, write,          # Module-level read/write functions
)
```

---

### EnumValue

```python
@dataclass(frozen=True)
class EnumValue:
    name: str          # Symbolic name (valid Python identifier)
    value: float       # Numeric value
    desc: str = ""     # Optional description

# Usage
EnumValue("START", 1, "Start conversion")
EnumValue("STOP", 0, "Stop conversion")
```

---

### FixedPointNumber & BinaryCodedDecimal

```python
@dataclass(frozen=True)
class FixedPointNumber:
    signed: str        # "U" or "S"
    integer_bits: int  # Total bits (including fractional)
    fractional_bits: int

@dataclass(frozen=True)
class BinaryCodedDecimal:
    pass  # No parameters needed

# Parsing from string
from rgscore.model.register import parse_number_format
fmt = parse_number_format("U8.0")   # FixedPointNumber("U", 8, 0)
fmt = parse_number_format("S4.2")   # FixedPointNumber("S", 4, 2)
fmt = parse_number_format("BCD")    # BinaryCodedDecimal()
```

---

### FieldDef

```python
@dataclass
class FieldDef:
    name: str
    offset: int                    # LSB position (0 = rightmost)
    width: int                     # Bit width
    number_format: NumberFormat    # FixedPointNumber | BinaryCodedDecimal
    rw: bool                       # True = read/write, False = read-only
    desc: str = ""
    enum_values: list[EnumValue] | None = None

# Factory methods
FieldDef.value_of("field@[7:0]U8.0#rw")  # From string
FieldDef.value_of(...).with_description("desc").with_enum([...])

# Convenience function
from rgscore import Field
Field(name="field", offset=0, numeric_type="U8.0", rw="rw", desc="", values=[...], width=None)

# Properties & Methods
fd.num_type()           # -> "U8.0" or "BCD"
fd.rw_mode()            # -> "rw" or "ro"
fd.bit_range_str()      # -> "[7:0]"
fd.end_offset()         # -> 7 (MSB)
fd.idxs()               # -> [0, 1, ..., 7]
fd.range()              # -> (min_val, max_val) as floats
fd.format(value)        # Format value as string per numeric type
fd.read(bitarray)       # Extract field value from register bitarray
fd.write(bitarray, val) # Write value into register bitarray
fd.get_next_raw_field(bitarray, step)  # For next_up/next_down
fd.copy()               # Deep copy
```

**Validation Rules:**
- Offset >= 0
- Field must fit within register width
- FixedPointNumber: `integer_bits == width`
- BCD: `width` must be provided explicitly
- Enum names and values must be unique

---

### Register

```python
class Register:
    def __init__(
        self,
        bit_len: int,                          # Register width in bits (> 0)
        model: list[FieldDef] | None = None,   # Field definitions
        address: int | None = None,            # Register address
        address_bus_width_bytes: int = 1,      # Address bus width
        name: str | None = None,               # Register name (valid identifier)
        link: RLink | None = None,             # Hardware link
        desc: str = "",                        # Description
        reset: str | BitArray | int = 0,       # Reset/initial value
    )

# If model is None: creates implicit field "val" spanning entire register as U{bit_len}.0

# Properties
reg.name                      # str | None
reg.address                   # int | None
reg.address_bus_width_bytes   # int
reg.desc                      # str
reg.width                     # int (bits)
reg.reset_value               # BitArray (copy)
reg.data                      # BitArray (current value, mutable)
reg.linked_address            # int | None (address used for hardware access)

# Field Access
reg.get_field_names()                     # -> list[str] (sorted by decreasing offset)
reg.get_field_definition(name)            # -> FieldDef
reg.get_field_value(name)                 # -> float | int (interpreted value)
reg.get_field_value_raw(name)             # -> BitArray (raw bits)
reg.get_field_enum_value(name)            # -> EnumValue | float | int
reg.set_field_value(name, value)          # -> float | int (actual value set)
reg.get_field_values()                    # -> dict[str, float]
reg.get_next_up_field_value(name)         # -> next larger discrete value
reg.get_next_down_field_value(name)       # -> next smaller discrete value

# Value can be: float, int, str (enum name), or EnumValue

# Model Management
reg.replace_model(new_fields: list[FieldDef])  # Replace entire field model
reg.copy()                                      # Deep copy with data

# Hardware Link
reg.link(link: RLink, register_address: int | None = None)
reg.read()   -> bool  # Read from hardware, update data, return True if linked
reg.write(read_back: bool = False, if_changed_only: bool = False) -> bool

# Change Tracking
reg.is_changed()  -> bool  # True if data != original_data since last read/write

# Serialization
reg.to_dict_def()     -> dict
reg.to_json_def(indent=None) -> str
Register.from_dict_def(dict) -> Register
Register.from_json_def(str)  -> Register

# Display
reg.pretty_print()    # Prints formatted table to stdout
repr(reg)             # "Name[0xADDR](field1=val, field2=val, ...)"
str(reg)              # Same as repr

# Embedding Class (for interactive use)
reg.mk_embedding_class(link: RLink | None) -> HardwareRegister
```

---

### HardwareRegister (Interactive Embedding)

Returned by `Register.mk_embedding_class()` and accessible via `dut.REG_NAME`.

```python
class HardwareRegister:
    # Field access as properties
    hr.field_name           # Get field value (float/int)
    hr.field_name = value   # Set field value
    hr.field_name_raw       # Get raw BitArray for field
    
    # Hardware operations
    hr.__read_through_link__()  -> bool
    hr.__write_through_link__() -> bool
    
    # Raw register data
    hr()  -> BitArray  # Current register bitarray
    
    # Representation
    repr(hr)  # Same as underlying register
```

---

### AddrMap

Container for ordered, unique registers with serialization and hardware linking.

```python
class AddrMap:
    def __init__(
        self,
        device: Device = default_device,                    # Device identification
        link: RLink | None = None,                          # Hardware link for all registers
        on_change_callback: Callable[[AddrMap], None] = ..., # Called on add/delete/update
        registers: list[Register] | None = None,            # Initial registers
        allow_multiple_registers_at_the_same_address: bool = False,
    )

# Properties
am.device
am.registers          # list[Register] (sorted by address)
am.regList            # RegList (interactive model access)
am.dut                # DeviceUnderTest (interactive hardware access)
am.allow_multiple_registers_at_the_same_address

# Register Management
am.add(register | list[Register])                           # Add register(s)
am.get_register_by_name(name)       -> Register | None
am.get_register_by_address(addr)    -> list[Register] | None
am.delete_register_by_name(name)    # NO-OP if not found
am.update_register_def(old_reg, new_reg)  # Atomic replace
am.clear()                          # Remove all registers

# Bulk Hardware Operations
am.read_all()   # Read all linked registers
am.write_all()  # Write all linked registers

# Linking
am.link(link: RLink)  # Link all registers to hardware

# Serialization
am.to_json_def(indent=None) -> str
AddrMap.from_json_def(json_str, link=None) -> AddrMap
AddrMap.new_instance_from_file(path, link=None) -> AddrMap
AddrMap.new_instance_from_url(url, link=None, cache=True, force_reload=False) -> AddrMap
am.save_to_json_file(path)  # Write to file
```

---

### RegList (Interactive Model Access)

Accessed via `addr_map.regList`. Provides read-only model inspection.

```python
regList = addr_map.regList

# List registers
regList()  -> list[str]  # Register names

# Access register model
regList.REG_NAME              # -> FieldModelAccessor
regList.REG_NAME()            # -> list[str] (field names)
regList.REG_NAME.FIELD_NAME   # -> FieldModelEnumAccessor
regList.REG_NAME.FIELD_NAME() # -> list[EnumValue] | None
regList.REG_NAME.FIELD_NAME(value) -> EnumValue | value | None

# Print register summary
print(regList.REG_NAME)
```

**FieldModelAccessor** shows: name, address, description, width, reset, fields
**FieldModelEnumAccessor** shows: name, bit range, num type, access, description, enums

---

### DeviceUnderTest (Interactive Hardware Access)

Accessed via `addr_map.dut`. Provides live register access.

```python
dut = addr_map.dut

# Access register
dut.REG_NAME        # -> HardwareRegister

# Field access
dut.REG_NAME.field_name       # Get value
dut.REG_NAME.field_name = val # Set value

# Hardware operations
from rgscore import read, write

read(dut.REG_NAME)      # Read from hardware
write(dut.REG_NAME)     # Write to hardware
read(dut.REG1, dut.REG2)  # Batch read
write(dut.REG1, dut.REG2) # Batch write

# Raw register data
dut.REG_NAME()  -> BitArray
```

---

### RLink & RLinkI2C (Hardware Abstraction)

```python
class RLink(ABC):
    @abstractmethod
    def read(addr: int, address_bus_width: int, value_width: int) -> BitArray | None
    @abstractmethod
    def write(addr: int, address_bus_width: int, value: BitArray) -> bool

class RLinkI2C(RLink):
    def __init__(self, i2c: I2CMaster, device_address: int, use_restart: bool = False)
    
    # i2c: instance from i2c-api (e.g., I2CMasterI2CDriver from i2c-drivers)
    # device_address: 7-bit I2C address
    # use_restart: Use repeated start for read (some devices don't support)
```

---

### S & U (Multi-Register Fixed-Point Composition)

```python
from rgscore import S, U

# Combine multiple register fields into a larger fixed-point value
# S(en, [bitarrays]) -> signed fixed-point with 'en' fractional bits
# U(en, [bitarrays]) -> unsigned fixed-point with 'en' fractional bits

# Example: 24-bit signed temperature across 3 registers (16 fractional bits)
temp_c = S(16, [
    dut.TEMP_DATA_MSB.temp_23_16,   # High 8 bits
    dut.TEMP_DATA_LSB.temp_15_8,    # Middle 8 bits
    dut.TEMP_DATA_XLSB.temp_7_0,    # Low 8 bits
])
# Result: float with 16 fractional bits
```

---

### Device

```python
@dataclass(frozen=True)
class Device:
    make: str
    model: str
    revision: str | None

default_device = Device("Acme", "Toaster", revision="1")
```

---

## JSON Schema (AddrMap)

The JSON format follows `addrMap-schema.json`. Key structure:

```json
{
  "class": "AddrMap",
  "allow_multiple_registers_at_the_same_address": false,
  "version": 1,
  "device": {
    "make": "Bosch",
    "model": "BMP581",
    "revision": "1.0"
  },
  "registers": [
    {
      "name": "CMD",
      "address": "0x7E",
      "address_bus_width_bytes": 1,
      "width": 8,
      "desc": "Command register",
      "reset": "0b00000000",
      "fields": [
        {
          "name": "cmd",
          "offset": 0,
          "width": 8,
          "number_format": {
            "class": "FixedPointNumber",
            "signed": "U",
            "integer_bits": 8,
            "fractional_bits": 0
          },
          "rw": true,
          "desc": "Command code",
          "enum_values": [
            {"name": "soft_reset", "value": 182, "desc": "Soft reset"},
            {"name": "nvm_write_en", "value": 160, "desc": "Enable NVM write"}
          ]
        }
      ]
    }
  ]
}
```

**Field number_format** can be:
```json
// Fixed-point
{"class": "FixedPointNumber", "signed": "U", "integer_bits": 8, "fractional_bits": 0}

// BCD
{"class": "BinaryCodedDecimal"}
```

---

## Complete Examples

### Example 1: Basic Register Definition

```python
from rgscore import Register, FieldDef, EnumValue, AddrMap

# Create register with fields defined via string
reg = Register(
    bit_len=8,
    name="CTRL",
    address=0x10,
    desc="Control register",
    model=[
        FieldDef.value_of("mode@[2:0]U3.0#rw")
            .with_description("Operating mode")
            .with_enum([
                EnumValue("SLEEP", 0, "Low power sleep"),
                EnumValue("STANDBY", 1, "Standby"),
                EnumValue("ACTIVE", 2, "Active measurement"),
            ]),
        FieldDef.value_of("int_en@[3]U1.0#rw").with_description("Interrupt enable"),
        FieldDef.value_of("status@[7:4]U4.0#ro").with_description("Device status"),
    ],
    reset=0x00,
)

# Access fields
print(reg.get_field_names())  # ['status', 'int_en', 'mode']
reg.set_field_value("mode", "ACTIVE")  # Set via enum name
reg.set_field_value("int_en", 1)
print(reg.get_field_value("mode"))  # 2.0
print(repr(reg))  # CTRL[0x10](status=0, int_en=1, mode=2)

# Pretty print
reg.pretty_print()
```

Output:
```
Register: CTRL
  Description: Control register
  Address:     0x10
  Width (bits): 8
  Reset data:  0b00000000
  Raw data:    0b00011000
  Fields:
  status  [7:4] U4.0 ro => 0
  int_en  [3]   U1.0 rw => 1
  mode    [2:0] U3.0 rw => 2 # Operating mode
    > ACTIVE    2    Active measurement
    > SLEEP     0    Low power sleep
    > STANDBY   1    Standby
```

---

### Example 2: Address Map with Serialization

```python
from rgscore import AddrMap, Register, FieldDef, EnumValue, Device
from pathlib import Path

# Create device info
device = Device("Bosch", "BMP581", revision="1.0")

# Create address map
addr_map = AddrMap(device=device)

# Add registers
addr_map.add([
    Register(bit_len=8, name="CMD", address=0x7E,
        model=[FieldDef.value_of("cmd@[7:0]U8.0#rw").with_enum([
            EnumValue("soft_reset", 0xB6),
            EnumValue("nvm_write_en", 0xA0),
        ])]),
    Register(bit_len=8, name="CHIP_ID", address=0x00,
        model=[FieldDef.value_of("id@[7:0]U8.0#ro")]),
    Register(bit_len=16, name="TEMP_DATA", address=0x1D,
        model=[
            FieldDef.value_of("temp_lsb@[7:0]U8.0#ro"),
            FieldDef.value_of("temp_msb@[15:8]U8.0#ro"),
        ]),
])

# Save to JSON file
addr_map.save_to_json_file("bmp581_addr_map.json")

# Load from file
loaded_map = AddrMap.new_instance_from_file("bmp581_addr_map.json")

# Load from URL (with caching)
web_map = AddrMap.new_instance_from_url(
    "https://example.com/addr_maps/bmp581.json",
    cache=True,
    force_reload=False,
)
```

---

### Example 3: Hardware Access via I2C

```python
from i2c_drivers import I2CMasterI2CDriver
from rgscore import AddrMap, RLinkI2C, read, write

# Setup I2C
i2c = I2CMasterI2CDriver("/dev/ttyUSB0")  # Or I2CMasterMCP2221, I2CMasterFT232H
link = RLinkI2C(i2c, device_address=0x47, use_restart=False)

# Load address map with hardware link
addr_map = AddrMap.new_instance_from_url(
    "https://raw.githubusercontent.com/Brainless-Software/rgscore/refs/heads/master/devices/AddrMap_BMP581.json",
    link=link
)

# Direct register access
cmd_reg = addr_map.get_register_by_name("CMD")
cmd_reg.read()
print(f"CMD value: {cmd_reg.get_field_value('cmd')}")

# Issue soft reset
cmd_reg.set_field_value("cmd", "soft_reset")  # or 0xB6
cmd_reg.write(read_back=True)

# Read temperature data
temp_reg = addr_map.get_register_by_name("TEMP_DATA")
temp_reg.read()
temp_raw = (temp_reg.get_field_value("temp_msb") << 8) | temp_reg.get_field_value("temp_lsb")
# Convert per datasheet...
```

---

### Example 4: Interactive API (REPL/Jupyter)

```python
from i2c_drivers import I2CMasterI2CDriver
from rgscore import AddrMap, RLinkI2C, read, write, S
import time

# Setup
i2c = I2CMasterI2CDriver("/dev/ttyUSB0")
link = RLinkI2C(i2c, 0x47)
addr_map = AddrMap.new_instance_from_url(
    "https://raw.githubusercontent.com/Brainless-Software/rgscore/refs/heads/master/devices/AddrMap_BMP581.json",
    link=link
)

# Get interactive handles
dut = addr_map.dut      # Device Under Test - live hardware access
regList = addr_map.regList  # Model inspection

# Explore registers
print(regList())  # List all register names
print(regList.CMD)  # Show CMD register model
print(regList.CMD())  # ['cmd']
print(regList.CMD.cmd())  # [soft_reset(182), nvm_write_en(160)]

# Issue soft reset
dut.CMD.cmd = regList.CMD.cmd.soft_reset
write(dut.CMD)
time.sleep(0.002)

# Configure power mode
read(dut.ODR_CONFIG)
dut.ODR_CONFIG.pwr_mode = regList.ODR_CONFIG.pwr_mode.Forced
write(dut.ODR_CONFIG)

# Wait and read temperature (3 registers)
read(dut.TEMP_DATA_LSB, dut.TEMP_DATA_XLSB, dut.TEMP_DATA_MSB)

# Combine into 24-bit signed value with 16 fractional bits
temp_c = S(16, [
    dut.TEMP_DATA_MSB.temp_23_16,
    dut.TEMP_DATA_LSB.temp_15_8,
    dut.TEMP_DATA_XLSB.temp_7_0,
])
print(f"Temperature: {temp_c} °C")

# Continuous measurement loop
for _ in range(60):
    dut.ODR_CONFIG.pwr_mode = regList.ODR_CONFIG.pwr_mode.Forced
    write(dut.ODR_CONFIG)
    time.sleep(1)
    read(dut.TEMP_DATA_LSB, dut.TEMP_DATA_XLSB, dut.TEMP_DATA_MSB)
    temp_c = S(16, [
        dut.TEMP_DATA_MSB.temp_23_16,
        dut.TEMP_DATA_LSB.temp_15_8,
        dut.TEMP_DATA_XLSB.temp_7_0,
    ])
    print(f"{temp_c:.2f} °C")
```

---

### Example 5: BCD Fields

```python
from rgscore import Register, FieldDef

# BCD field requires explicit width
reg = Register(
    bit_len=8,
    name="RTC_DATE",
    address=0x04,
    model=[
        FieldDef.value_of("day@[7:0]BCD").with_description("Day of month (1-31)"),
    ],
)

# Valid range: 0-31 (encoded as BCD: 0x01-0x31)
reg.set_field_value("day", 15)
print(reg.get_field_value_raw("day"))  # 0b00010101 (0x15)
print(reg.get_field_value("day"))      # 15

reg.set_field_value("day", 31)
print(reg.get_field_value_raw("day"))  # 0b00110001 (0x31)

# Invalid - would raise ValueError
# reg.set_field_value("day", 32)  # Out of range
# reg.set_field_value("day", 15.5)  # Not integer
```

---

### Example 6: Fixed-Point Arithmetic

```python
from rgscore import Register, FieldDef

# S4.2 = 4 bits signed, 2 fractional bits
# Range: -2.0 to +1.75, step = 0.25
reg = Register(
    bit_len=8,
    name="GAIN",
    address=0x20,
    model=[
        FieldDef.value_of("gain@[3:0]S4.2#rw").with_description("Gain factor"),
        FieldDef.value_of("offset@[7:4]S4.0#rw").with_description("Offset"),
    ],
)

# Set values (automatically quantized to 0.25 steps)
reg.set_field_value("gain", 1.5)    # Exact: 1.5
reg.set_field_value("gain", 1.3)    # Quantized to 1.25
print(reg.get_field_value("gain"))  # 1.25

reg.set_field_value("gain", -1.75)  # Minimum
reg.set_field_value("gain", 1.75)   # Maximum

# Next up/down
print(reg.get_next_up_field_value("gain"))    # -1.5
print(reg.get_next_down_field_value("gain"))  # -1.75 (already at min)
```

---

### Example 7: Custom RLink Implementation

```python
from rgscore import RLink, Register, AddrMap
from bitstring import BitArray

class SimulatedLink(RLink):
    """In-memory register simulator for testing."""
    
    def __init__(self):
        self.memory = {}
    
    def read(self, addr: int, address_bus_width: int, value_width: int) -> BitArray | None:
        return self.memory.get(addr)
    
    def write(self, addr: int, address_bus_width: int, value: BitArray) -> bool:
        self.memory[addr] = value.copy()
        return True

# Usage
link = SimulatedLink()
link.memory[0x10] = BitArray("uint:8=0x55")

addr_map = AddrMap(link=link)
addr_map.add(Register(bit_len=8, name="TEST", address=0x10,
    model=[FieldDef.value_of("val@[7:0]U8.0#rw")]))

reg = addr_map.get_register_by_name("TEST")
reg.read()
print(reg.get_field_value("val"))  # 85.0

reg.set_field_value("val", 0xAA)
reg.write()
print(link.memory[0x10].hex)  # 'aa'
```

---

## Error Handling

| Operation | Exception | Condition |
|-----------|-----------|-----------|
| `Register()` | `ValueError` | Invalid name, width <= 0, empty model, overlapping fields, field out of bounds |
| `FieldDef.value_of()` | `ValueError` | Invalid string format |
| `FieldDef.with_enum()` | `ValueError` | Duplicate enum names or values |
| `set_field_value()` | `ValueError` | Field not found, read-only field, value out of range, invalid enum |
| `reg.link()` | `ValueError` | No address provided |
| `reg.read()` | `ValueError` | No register at address (hardware) |
| `AddrMap.add()` | `ValueError` | Duplicate name/address |
| `AddrMap.from_json_def()` | `ValueError` | Invalid JSON structure/version |
| `AddrMap.new_instance_from_url()` | `HTTPError` | Non-200 response |

---

## Best Practices

1. **Define registers in JSON** - Version control, share across projects/languages
2. **Use enums** - Self-documenting, prevents invalid values
3. **Load from URL with cache** - Fast startup, works offline after first load
4. **Use `dut`/`regList` for interactive work** - Clean REPL experience
5. **Batch reads/writes** - `read(reg1, reg2)`, `write(reg1, reg2)` for efficiency
6. **Use `S()`/`U()` for multi-register values** - Handles bit concatenation correctly
7. **Set `use_restart=False` for I2C** - Better compatibility, only enable if device requires
8. **Check `is_changed()` before write** - Avoid unnecessary bus traffic

---

## Common Patterns

### Pattern: Register with Reserved Bits
```python
model=[
    FieldDef.value_of("ctrl@[1:0]U2.0#rw"),
    FieldDef.value_of("reserved@[7:2]U6.0#ro").with_description("Reserved, read as 0"),
]
```

### Pattern: Bit Flags
```python
model=[
    FieldDef.value_of("en_temp@[0]U1.0#rw").with_enum([EnumValue("DIS", 0), EnumValue("EN", 1)]),
    FieldDef.value_of("en_press@[1]U1.0#rw").with_enum([EnumValue("DIS", 0), EnumValue("EN", 1)]),
    FieldDef.value_of("int_latch@[2]U1.0#rw").with_enum([EnumValue("PULSED", 0), EnumValue("LATCHED", 1)]),
]
```

### Pattern: Multi-Register Value (S/U)
```python
# 32-bit unsigned across two 16-bit registers
value = U(0, [reg_high.data, reg_low.data])

# 24-bit signed with 8 fractional bits across 3 registers
value = S(8, [msb.field, mid.field, lsb.field])
```

### Pattern: Conditional Write
```python
if reg.is_changed():
    reg.write()
# Or use:
reg.write(if_changed_only=True)
```

---

## Related Projects

- **i2c-api** - Abstract I2C master interface
- **i2c-drivers** - Concrete I2C implementations (FT232H, MCP2221, I2CDriver, Linux I2C)
- **rgscore** - This library (register modeling + access)

---

## License

MIT License - Copyright (c) Dmitri Priimak