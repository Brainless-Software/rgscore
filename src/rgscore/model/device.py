from dataclasses import dataclass


@dataclass(frozen=True)
class Device:
    """Device make, model and revision placed in the AddrMap"""

    make: str
    model: str
    revision: str | None

    def __repr__(self) -> str:
        return f"{self.make} :: {self.model}" + ("" if self.revision is None else f" :: {self.revision}")


default_device = Device("Acme", "Toaster", revision="1")
"""
Default Device used in the constructor of AddrMap.
"""
