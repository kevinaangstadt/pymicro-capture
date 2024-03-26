# pymicro-capture
Capture a grid of images using a Marlin Microscope Stage and Leica Microscope

# Setup
MacOS and Linux systems will need `libusb` installed to function correctly. Mac
systems can install this using `brew`, and this is a commonly supported package
on most Linux distributions.

## Virtual Environment
Create a virtual environment and activate it.

In unix-like environments:
```shell
python3 -m venv .venv
source .venv/bin/activate
```

In Windows with powershell:
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

## Install Dependencies

```shell
pip install wheel
pip install -r requirements.txt
```