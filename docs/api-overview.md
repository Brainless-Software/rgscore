# API Overview

To fulfill above goals this library defines following classes and functions:

## Classes

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
* `AddrMap` - grouping of registers ensuring their uniqueness within addrMap. Primary class for (de)serialization
  to/from json file.
* `DeviceUnderTest` - class available at `AddrMap::dut`. It provided interactive read and write access to registers
  on physical hardware.
* `RegList` - class available at `AddrMap::regList`. It provides minimal necessary model information about registers
  contained in this `AddrMap`.

## Functions

* `read(...)` - reads data from live hardware into register present under `dut` (Device Under Test).
* `write(...)` - writes data from register present under `dut` into physical hardware.
* `AddrMap.new_instance_from_file(...)` - creates instance of `AddrMap` based on json file that holds serialized form of
  address map.
* `AddrMap.new_instance_from_url(...)` - creates instance of `AddrMap` based on json file present at the provided url.
