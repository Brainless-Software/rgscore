import json
from collections.abc import Callable
from typing import Self

from rgscore.model.register import Register, RLink


class RegList:
    def __init__(
        self,
        store: RLink | None = None,
        on_change_callback: Callable[[Self], None] = lambda _: None,
        registers: list[Register] | None = None,
    ):
        super().__init__()
        self.registers: list[Register] = []
        self._reg_names: set[str] = set()
        self._reg_addresses: set[int] = set()
        self._reg_by_names: dict[str, Register] = {}
        self._reg_by_address: dict[int, Register] = {}
        self._store = store
        self._on_change_callback = on_change_callback

        if registers is not None:
            self.add(registers)

    def add(self, rs: Register | list[Register]):
        self.__add(rs, call_on_change_callback=True)

    def __add(self, rs: Register | list[Register], call_on_change_callback: bool):
        rs = [rs] if isinstance(rs, Register) else rs
        if len(rs) == 0:
            return

        for r in rs:
            if r.address is None:
                raise ValueError("To be added Register must have an address")

            if r.name is None:
                # create implicit register name if register does not an explicit one
                r.name = f"R{r.address}"

            if r.name in self._reg_names:
                raise ValueError(f"Register under a name [{r.name}] is already in the set")

            if r.address in self._reg_addresses:
                raise ValueError(f"Register at this address [0x{r.address:04X}] is already in the set")

            if self._store is not None:
                r.link(self._store)

            self.registers.append(r)
            self._reg_names.add(r.name)
            self._reg_addresses.add(r.address)
            self._reg_by_names[r.name] = r
            self._reg_by_address[r.address] = r

        self.registers.sort(key=lambda r: r.address)
        if call_on_change_callback:
            self._on_change_callback(self)

    def get_register_by_name(self, name: str) -> Register | None:
        return self._reg_by_names.get(name)

    def get_register_by_address(self, address: int) -> Register | None:
        return self._reg_by_address.get(address)

    def delete_register_by_name(self, name: str):
        self.__delete_register_by_name(name, call_on_change_callback=True)

    def __delete_register_by_name(self, name: str, call_on_change_callback: bool):
        """
        Removes register with a given name from this regList. If register with this name not found, then do nothing.
        """
        if name in self._reg_names:
            register = self._reg_by_names[name]
            self._reg_names.remove(name)

            assert register.address is not None
            self._reg_addresses.remove(register.address)
            del self._reg_by_names[name]
            del self._reg_by_address[register.address]

            idx = [r.name for r in self.registers].index(name)
            del self.registers[idx]
            if call_on_change_callback:
                self._on_change_callback(self)

    def update_register_def(self, original_register: Register, new_register: Register) -> None:
        """
        Updates register in the regList given the original one and a new one which is expected to replace original.
        """
        if new_register.address is None:
            raise ValueError("To be added Register must have an address")

        if new_register.name is None:
            raise ValueError("To be added Register must have a name")

        if new_register.name != original_register.name and new_register.name in self._reg_names:
            raise ValueError(f"Register under a name [{new_register.name}] is already in the set")

        if new_register.address != original_register.address and new_register.address in self._reg_addresses:
            raise ValueError(f"Register at this address [{new_register.address}] is already in the set")

        assert original_register.name is not None
        self.__delete_register_by_name(original_register.name, call_on_change_callback=False)
        self.__add(new_register, call_on_change_callback=False)
        self._on_change_callback(self)

    def clear(self):
        """Removes all registers from the list."""
        self.registers.clear()
        self._reg_names.clear()
        self._reg_addresses.clear()
        self._reg_by_names.clear()
        self._reg_by_address.clear()
        self._on_change_callback(self)

    def read_all(self) -> None:
        """Reads all registers in the regList from linked store if any provided."""
        for r in self.registers:
            r.read()

    def write_all(self) -> None:
        """Writes all registers in the regList to linked store if any provided."""
        for r in self.registers:
            r.write()

    def to_json_def(self, indent: int | None = None) -> str:
        """Exports register definition contained within regList as json text."""
        return json.dumps(
            {
                "class": "RegList",
                "version": 1,
                "registers": [r.to_dict_def() for r in self.registers],
            },
            indent=indent,
        )

    @staticmethod
    def from_json_def(json_str: str) -> "RegList":
        """Imports a RegList definition from a json string returning new instance of RegList."""
        return RegList().load_from_json_def(json_str)

    def load_from_json_def(self, json_str: str) -> Self:
        data = json.loads(json_str)
        if data["class"] != "RegList":
            raise ValueError("Provided json document does not represent regList")
        elif data["version"] != 1:
            raise ValueError(f"Provided regList json has unsupported version {data['version']}")
        else:
            self.clear()
            self.add([Register.from_dict_def(d) for d in data["registers"]])
        return self
