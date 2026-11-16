To access physical hardware you need to create instance of `RLink` that
links `AddrMap` (and therefore registers) to live chip over some physical bus.
Below is an example of doing that over I2C bus. This requires you to bring in
two more libraries, [i2c-api](https://brainless-software.github.io/i2c_api/)
and [i2c-drivers](https://github.com/Brainless-Software/i2c_drivers).

```python
from i2c_drivers import I2CMasterI2CDriver

from rgscore import AddrMap, RLinkI2C

addrMap = AddrMap.new_instance_from_file("addrMap-BMP581.json", link=RLinkI2C(I2CMasterI2CDriver(), 0x47))

odr_config = addrMap.get_register_by_name("ODR_CONFIG")
odr_config.read()  # read from the chip at I2C address 0x47
print("pwr_mode", odr_config.get_field_value("pwr_mode"))

# set new pwr_mode and write this register to the chip
odr_config.set_field_value("pwr_mode", 1)
odr_config.write()
```
