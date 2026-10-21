import time

import pytest
import serial.tools.list_ports as slp
from bitstring import BitArray
from i2c_api import I2CTransactionBuilder, RegisterAddress
from i2c_drivers import I2CMasterI2CDriver

from rgscore import FieldDef, Register, RegList, RLink, RLinkI2C, S, U

# Attempt to autodetect com port for I2CDriver; This works on Linux only.
ports = [p.device for p in slp.comports() if p.product == "FT230X Basic UART"]
port = "/dev/ttyUSB0" if ports == [] else ports[0]

i2c_master = I2CMasterI2CDriver(port)


@pytest.fixture
def bmp581_address() -> int:
    return 0x47


@pytest.fixture()
def link(bmp581_address: int) -> RLink:
    return RLinkI2C(i2c_master, bmp581_address)


rs = RegList(RLinkI2C(I2CMasterI2CDriver(port), 0x47))
rs.add(
    Register(
        bit_len=8,
        address=0x37,
        name="ODR_CONFIG",
        model=[
            FieldDef.value_of("deep_dis@[7:7]U1.0"),
            FieldDef.value_of("odr@[6:2]U5.0"),
            FieldDef.value_of("pwr_mode@[1:0]U2.0"),
        ],
    )
)
rs.add(Register(bit_len=8, address=0x7E, name="CMD", model=[FieldDef.value_of("cmd@[7:0]U8.0")]))


class TestBMP581:
    def test_read_id_registers(self, bmp581_address: int):
        asic_id_regval = i2c_master.read_register(bmp581_address, RegisterAddress(0x01, 1))
        assert asic_id_regval.bin == "01010000"

    def test_odr_register(self, link: RLink):
        odr_register = rs.get_register_by_name("ODR_CONFIG")
        odr_register.read()

        # this register should come up with all values reset to default values which are as follows:
        assert odr_register.get_field_value("deep_dis") == 0
        assert odr_register.get_field_value("odr") == 0x1C  # 1Hz frequency for measurements
        assert odr_register.get_field_value("pwr_mode") == 0

        # change frequency for measurements to 0x1F (measure every 1/4 of a second)
        odr_register.set_field_value("odr", 0x1F)
        assert odr_register.get_field_value("odr") == 0x1F  # 0.125Hz frequency for measurements
        # but data is not written out to the device; we will read it now to confirm that it is so
        odr_register.read()
        assert odr_register.get_field_value("odr") == 0x1C  # 1Hz frequency for measurements
        # change it again and now write it to the device
        odr_register.set_field_value("odr", 0x1F)
        odr_register.write()
        odr_register.read()
        assert odr_register.get_field_value("odr") == 0x1F  # 0.125Hz frequency for measurements

        # now issue reset and read back odr_register and confirm that odr value is back to default value
        rs.get_register_by_name("CMD").set_field_value("cmd", 0xB6)
        rs.get_register_by_name("CMD").write()
        # according to the spec device should be unresponsive for 2ms. So to proceed we will wait 5 millis.
        time.sleep(0.005)
        odr_register.read()
        assert odr_register.get_field_value("odr") == 0x1C  # 1Hz frequency for measurements

    def test_sequential_read_using_i2c_language(self, bmp581_address):
        result = (
            I2CTransactionBuilder()
            .start()
            .address(bmp581_address)
            .write(1)
            .restart()
            .address(bmp581_address)
            .read(2)
            .stop()
            .exec(i2c_master)
        )
        assert result.is_success

        assert result.data[0] == [BitArray("0x50"), BitArray("0x32")]

        # confirm that we can use U and S with arrays of integers
        assert U(2, result.data[0]) == 5132.5
        assert S(2, result.data[0]) == 5132.5
