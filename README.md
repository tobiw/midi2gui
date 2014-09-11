midi2gui
========

Translates MIDI messages into GUI commands and key shortcuts

To run, simply execute
  python midi2gui.py

To customize the mapping, search the code for the
  SHORTCUT_MAP = { ....
and edit the mapping. The key (left-hand side) is a tuple of MIDI channel, MIDI
message type (e.g. CTRL) and MIDI data byte 1 value (for CTRL messages, this is
the CC#). The value is an instance of a subclass of ActionBase.

The parameters for ShortcutAction are a tuple of modifiers (see the NO_MOD etc
constants) and the shortcut key as a single character. For ShortcutValueAction,
an additional parameter has to be given which is a function that calculates the
value we want to enter after pressing the key shortcut. This function usually
translates the MIDI control value (which ranges from 0 to 127) to the
applications value, e.g. -1.0 to +1.0.


Contact me:
Twitter: tobiaswulff
Email: code-tobi(a)swulff.de
Github: http://github.com/tobiw
