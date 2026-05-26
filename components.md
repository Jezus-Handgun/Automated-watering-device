# Components and purpose

This file explains what each component does and why we need it for the project.

## Core control
- Raspberry Pi 4 (x1) - runs the backend, controls GPIO, stores the SQLite file.
- microSD 32GB+ (x1) - system storage and logs.
- Power supply 5V/3A (x1) - stable power for Raspberry Pi.
- Case for RPi4 (x1) - protects the board; use a ventilated one.

## Sensors
- Capacitive soil moisture sensor, analog (x1) - measures soil moisture for the single pot.
- MCP3008 ADC (x1) - converts analog sensor voltage to digital for Raspberry Pi (RPi has no analog input).
- Jumper wires + breadboard (x1 set) - connects sensors to MCP3008 and GPIO.

## Water amount measurement
- Flow meter with Hall sensor (x1) - outputs pulses proportional to water flow, so we can measure volume.
- Level shifter 5V to 3.3V (x1) - protects Raspberry Pi GPIO if the flow meter outputs 5V pulses.

## Actuators
- 12V pump (x1) - pushes water from the tank to the pot.
- 12V solenoid valve, normally closed (x1) - opens/closes the line to control when water flows.
- 2-channel relay module 5V (x1) OR 2x logic-level MOSFET (x2) - switches pump and valve on/off.
- Flyback diodes (x2, if MOSFETs without protection) - protect electronics from inductive spikes.

## Plumbing
- Water tank (x1) - reservoir.
- Tubing 1/4" or 6mm (2-5 m) - water line.
- Fittings (set) - connectors, elbows, etc.
- Check valve (x1) - prevents backflow.
- Inline filter (x1) - protects pump and valve from dirt.
- Dripper/emitter (x1) - stabilizes and reduces flow for a single pot.

## Power for actuators
- 12V power supply 2-5A (x1) - for pump and valve.
- Optional: step-down 12V to 5V/3A (x1) - if you want a single 12V supply for everything.
- Common ground - the 12V supply ground must be connected to Raspberry Pi ground.

## Outdoor enclosure
- IP65/IP67 enclosure (x1) - protects electronics from rain and dust.
- Cable glands (x4) - sealed cable entry.
- Heat-shrink tubes + cable ties (set) - secure wiring and insulation.

## Quantities summary (1 pot, 1 zone)
- Raspberry Pi 4 (1)
- microSD 32GB+ (1)
- 5V/3A PSU (1)
- Capacitive moisture sensor (1)
- MCP3008 ADC (1)
- Flow meter (1)
- Level shifter (1)
- Pump 12V (1)
- Solenoid valve 12V NC (1)
- Relay module 2ch (1) or MOSFETs (2)
- 12V PSU (1)
- Tubing + fittings + check valve + filter + dripper (1 set)
- Outdoor enclosure + glands (1 set)
