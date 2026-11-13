import hashlib
import json
from collections.abc import Callable
from os import getenv
from pathlib import Path
from typing import Self

import requests
from requests import HTTPError

from rgscore.model.register import Register, RLink


class AddrMap:
    def __init__(
        self,
        link: RLink | None = None,
        on_change_callback: Callable[[Self], None] = lambda _: None,
        registers: list[Register] | None = None,
    ):
        """
        Creates instance of AddrMap. An object that holds an ordered set of registers.
        Args:
            link: an external store (object that accesses physical hardware) to which to which all registers in
                this AddrMap are to be linked. Default is None, meaning that this AddrMap will be an in-memory only
                representation of register set.
            on_change_callback: function called when registers are added or removed to/from this AddrMap or changed.
            registers: optional list registers to be contained within this AddrMap. Register can later be added by
                calling AddrMap.add(...) method.
        """
        super().__init__()
        self.registers: list[Register] = []
        self._reg_names: set[str] = set()
        self._reg_addresses: set[int] = set()
        self._reg_by_names: dict[str, Register] = {}
        self._reg_by_address: dict[int, Register] = {}
        self._store = link
        self._on_change_callback = on_change_callback

        if registers is not None:
            self.add(registers)

    def __repr__(self):
        return f"AddrMap[len(registers)={len(self.registers)}]"

    def add(self, rs: Register | list[Register]) -> None:
        """Adds one or more registers to this AddrMap."""
        self.__add(rs, call_on_change_callback=True)

    def __add(self, rs: Register | list[Register], call_on_change_callback: bool) -> None:
        rs = [rs] if isinstance(rs, Register) else rs
        if len(rs) == 0:
            return

        for r in rs:
            if r.address is None:
                raise ValueError("To be added Register must have an address")

            if r.name is None:
                # create implicit register name if register does not an explicit one
                generated_register_name = f"R{r.address}"
                if generated_register_name in self._reg_names:
                    raise ValueError(
                        f"Register under a name [{generated_register_name}] is already preset in the AddrMap"
                    )
                r.name = generated_register_name

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
        """
        Returns register contained within this AddrMap by its name. If no such register exist
        in the AddrMap, then return None.
        """
        return self._reg_by_names.get(name)

    def get_register_by_address(self, address: int) -> Register | None:
        """
        Returns register contained within this AddrMap by its address. If no such register exist
        in the AddrMap, then return None.
        """
        return self._reg_by_address.get(address)

    def delete_register_by_name(self, name: str) -> None:
        """
        Deletes (removes) registers identified by register name from this AddrMap. If register under this name
        does not exist, then this is a NO-OP.
        """
        self.__delete_register_by_name(name, call_on_change_callback=True)

    def __delete_register_by_name(self, name: str, call_on_change_callback: bool):
        """
        Removes register with a given name from this AddrMap. If register with this name not found, then do nothing.
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
        Updates register in the AddrMap given the original one and a new one which is expected to replace original.
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
        """Reads all registers in the AddrMap from linked store if any provided."""
        for r in self.registers:
            r.read()

    def write_all(self) -> None:
        """Writes all registers in the AddrMap to linked store if any provided."""
        for r in self.registers:
            r.write()

    def to_json_def(self, indent: int | None = None) -> str:
        """
        Exports register definition contained within AddrMap as json text. Resulting json
        will confirm to the AddrMap-scheme.json schema file.
        """
        return json.dumps(
            {
                "class": "AddrMap",
                "version": 1,
                "registers": [r.to_dict_def() for r in self.registers],
            },
            indent=indent,
        )

    @staticmethod
    def from_json_def(json_str: str, link: RLink | None = None) -> "AddrMap":
        """
        Imports a AddrMap definition from a json string returning new instance of AddrMap. Input string must
        be a json document conforming to the AddrMap-scheme.json schema file.

        Args:
            json_str: string holding json serialization of AddrMap.
            link: optional RLink connecting this AddrMap to physical hardware. Default is None.

        Returns:
            New instance of AddrMap.
        """
        return AddrMap(link=link).__load_from_json_def(json_str)

    def __load_from_json_def(self, json_str: str) -> Self:
        data = json.loads(json_str)
        if data["class"] != "AddrMap":
            raise ValueError("Provided json document does not represent AddrMap")
        elif data["version"] != 1:
            raise ValueError(f"Provided AddrMap json has unsupported version {data['version']}")
        else:
            self.clear()
            self.add([Register.from_dict_def(d) for d in data["registers"]])
        return self

    @staticmethod
    def new_instance_from_file(file: Path | str, link: RLink | None = None) -> "AddrMap":
        """
        Creates instance of AddrMap from json data stored in the file.

        Args:
            file: name of the file.
            link: optional RLink connecting this AddrMap to physical hardware. Default is None.

        Returns:
            AddrMap: new instance with data loaded from the file.

        Raises:
            ValueError: if file contains an invalid json.
        """
        return AddrMap.from_json_def(Path(file).read_text())

    @staticmethod
    def new_instance_from_url(url: str, link: RLink | None = None, cache: bool = True,
                              force_reload: bool = False) -> "AddrMap":
        """
        Creates instance of AddrMap from json data stored in the url. Cache directory root will be ~/.rgscore/cache
        unless env. variable RGSCORE_CACHE_DIR is set.

        Args:
            link: optional RLink connecting this AddrMap to physical hardware. Default is None.
            url: URL pointing at the AddrMap json file.
            cache: If True, then load data from local cache or if it is not available in the cache load it
                from the URL and store results in the cache. If False, then always load from provided URL.
                Cache is in a directory ~/.rgscore/cache
            force_reload: If True and cache==True then load from URL even if data is available in the cache.
                If False, then load from URL only when data is not available in the cache. If cache==False,
                then this argument has no effect.

        Returns:
            AddrMap: new instance with data loaded from provided URL.

        Raises:
            ValueError: if file contains an invalid json.
            HttpError: if response code is not 200.
        """
        if cache:
            cache_file = hashlib.sha1(url.encode('utf-8')).hexdigest() + ".json"
            rgscore_cache_dir = getenv("RGSCORE_CACHE_DIR")
            cache_root = Path.home() / ".rgscore" / "cache" if rgscore_cache_dir is None else Path(rgscore_cache_dir)
            cache_dir = cache_root / cache_file[0:2] / cache_file[2:4]
            cache_file_path = cache_dir / cache_file
            if not cache_dir.exists():
                cache_dir.mkdir(parents=True, exist_ok=True)

            if force_reload or not cache_file_path.exists():
                response = requests.get(url)
                if response.status_code == 200:
                    json_source = response.text
                    cache_file_path.write_text(json_source)
                    return AddrMap.from_json_def(json_source, link)
                else:
                    raise HTTPError(f"Invalid response code {response.status_code}")
            else:
                return AddrMap.from_json_def(cache_file_path.read_text(), link)

        else:
            response = requests.get(url)
            if response.status_code == 200:
                return AddrMap.from_json_def(response.text, link)
            else:
                raise HTTPError(f"Invalid response code {response.status_code}")

    def save_to_json_file(self, file: Path | str) -> None:
        """ Save current AddrMap to json file. """
        Path(file).write_text(self.to_json_def())
