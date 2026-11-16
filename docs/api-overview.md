# API Overview

To fulfill above goals this library defines following classes and functions:

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