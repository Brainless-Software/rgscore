from timeit import dummy_src_name

# RGSCore

[![License - MIT](https://img.shields.io/badge/License-MIT-blue)](https://github.com/Brainless-Software/rgscore/blob/master/LICENSE)
[![PyPI Latest Release](https://img.shields.io/pypi/v/rgscore.svg)](https://pypi.org/project/rgscore/)
[![pytest](https://github.com/Brainless-Software/rgscore/actions/workflows/test.yml/badge.svg)](https://github.com/Brainless-Software/rgscore/actions/workflows/test.yml)
[![Documentation](https://img.shields.io/badge/docs-latest-brightgreen)](https://brainless-software.github.io/rgscore/)

Python library that provides classes for representing, defining and accessing registers in the embedded devices.

To add this library to your [uv](https://docs.astral.sh/uv) managed project do

```shell
uv add rgscore
```

Complete documentation is available [here](https://brainless-software.github.io/rgscore/).

## Trying example Juputer Notebook

Source code this library contains example [Jupyter Notebook](https://jupyter.org/). To use it as it is you need to
have [I2CDriver](https://i2cdriver.com/) and [BMP581](https://www.adafruit.com/product/6407) temperature and
pressure sensor.

To try it out do following.

First make sure that you have [uv](https://docs.astral.sh/uv) command line tool installed.

On Linux or Apple computers open a terminal and run

```shell
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Windows open PowerShell window and run

```shell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then in the terminal (or PowerShell) do following

```shell
git clone https://github.com/Brainless-Software/rgscore.git
cd rgscore
uv sync
uv run jupyter lab BMP581_Example.ipynb
```

Last command will start jupyter lab server and open browser with BMP581_Example.ipynb notebook opened.

## Building code with LLM using this library

File [LLM.md](https://raw.githubusercontent.com/Brainless-Software/rgscore/refs/heads/master/LLM.md) can be used
as an entry point by the AI agents to understand how API provided by this library works. 
