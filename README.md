# README.md

Python controller for DMX lighting over Art-Net.

## Structure

The project separates physical hardware configuration, fixture definitions, reusable effects, show scheduling and low-level transport.

`config/` contains the physical rig, fixture channel mappings, named colours and colour palettes.

`lights/` contains the reusable Python code for Art-Net transport, fixture control, effects, show loading and scheduling, and the overall rig abstraction.

`shows/` contains YAML show definitions such as the Halloween show. Each show combines independent colour, movement, intensity and strobe layers over a sequence of timed phases.

`tools/` contains standalone utilities for testing the Art-Net connection, raw DMX channels, fixture controls and individual lighting behaviours.

`run_show.py` is the main entry point for running a complete show.

## Current Hardware

### Pknight EasyNode BLUE

* Wi-Fi / Bluetooth Art-Net and sACN to DMX512 transceiver
* Bridges the Python controller to the physical DMX fixture
* Product: https://www.pknightpro.com/products/pknight-advanced-wireless-dmx-controller-easynode-blue-with-dual-wifi-bluetooth-connectivity-portable-rechargeable-sacn-art-net-interface
* Manual: https://pknight.cc/myfiles/usermanual/pknight_easynode_BLUE_manual.pdf

### ZQ06141 12-Beam RGBW Swing Wall Washer

* Motorised 12-beam RGBW DMX512 fixture
* Supports 7CH, 11CH and 55CH modes
* This project currently uses 11CH mode
* Product/manual page: https://manuals.plus/ae/1005009409599499
* DMX channel manual: https://manuals.plus/m/979cc9a5204d4316347bc806f986e9040779c708347b8dc2fbbe5cf34db506a7
