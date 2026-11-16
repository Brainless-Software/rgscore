# Initialize AddrMap from json store

## Loading addrMap from json file

Instance of `AddrMap` can writen down into json file and read back like so

```python
from pathlib import Path
from rgscore import AddrMap

addrMap = AddrMap(...)

# write into a file
addrMapFilePath = Path.home() / "addrMap.json"
addrMap.save_to_json_file(addrMapFilePath)

# load from a file
addrMap = AddrMap.new_instance_from_file(addrMapFilePath.read_text())
```

## Loading addrMap from URL

`AddrMap` class can be instantiated with the URL that points to addrMap json file.

```python
from rgscore import AddrMap

addrMap = AddrMap.new_instance_from_url("https://.../addrMap.json")
```

By default, this will cache downloaded json file at `$HOME/.rgscore/cache/`
directory, so that subsequent calls to this function will load addrMap from
cache. Cache can be refreshed if `force_reload=True` argument is set.

To change cache location you can set `RGSCORE_CACHE_DIR` environment variable
to another folder.
