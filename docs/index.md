# RGSCore

Python library that provides classes for representing, defining and accessing registers in the embedded devices.

To add this library to your project do

```shell
uv add rgscore
```

## Library purpose

1. Provide python API to define registers and serialize it into persistent json store/file.
2. Provide access from Python to serialized form of register definitions (aka. addrMap json).
3. Together with other libraries, such as [i2c-api](https://brainless-software.github.io/i2c_api/)
   and [i2c-drivers](https://github.com/Brainless-Software/i2c_drivers), to provide read and write access from Python to
   registers in live devices.
4. Provide intuitive interactive API for interfacing with live devices.
