import logging
import sys
import threading
from mididings import *
from mididings.extra import *
from subprocess import Popen, PIPE
from time import sleep

logging.basicConfig(level=logging.DEBUG)


class WindowManager(object):
    def get_active_window_title(self):
        raise NotImplementedError


class XorgWindowManager(WindowManager):
    def get_active_window_title(self):
        out = Popen(['xprop', '-root', '_NET_ACTIVE_WINDOW'], stdout=PIPE).communicate()
        logging.debug(out)
        if out[0]:
            window_id = out[0].split()[4]
            out = Popen(['xprop', '-id', window_id, 'WM_NAME'], stdout=PIPE).communicate()
            if out[0]:
                value = out[0].split('=', 1)[1]
                if value:
                    return value.strip()
        logging.error(out[1])

# ---------------------------------------------------------------------------


class ShortcutExecutor(object):
    def execute_key(self, key, modifiers):
        """Executes a key shortcut"""
        raise NotImplementedError

    def execute_key_value(self, key, modifiers, value):
        """Executes a key shortcut and enters a value"""
        raise NotImplementedError


class XteExecutor(ShortcutExecutor):
    @staticmethod
    def _execute(seq):
        logging.debug(seq)
        Popen(['xte'], stdin=PIPE).communicate(input=seq)

    def execute_key(self, key, modifiers):
        """
        Executes a key shortcut.
        """
        seq = self._make_shortcut_seq(key, modifiers[0], modifiers[1], modifiers[2])
        self._execute(seq)

    def execute_key_value(self, key, modifiers, value):
        """
        Executes a key + value shortcut.
        """
        seq = self._make_shortcut_seq(key, modifiers[0], modifiers[1], modifiers[2])
        seq += self._make_edit_seq(str(value))
        self._execute(seq)

    @staticmethod
    def _make_shortcut_seq(keys, ctrl, alt, shift):
        if len(keys) > 1:
            s = ['str ' + keys]
        else:
            s = ['key ' + keys]
        if ctrl:
            s = ['keydown Control_L'] + s + ['keyup Control_L']
        if alt:
            s = ['keydown Alt_L'] + s + ['keyup Alt_L']
        if shift:
            s = ['keydown Shift_L'] + s + ['keyup Shift_L']
        return '\n'.join(s) + '\n'

    @staticmethod
    def _make_edit_seq(v):
        return '\n'.join(['str ' + str(v), 'key Return']) + '\n'

# ---------------------------------------------------------------------------


class ActionBase(object):
    def __init__(self, modifiers, key, func=None):
        self._modifiers = modifiers
        self._key = key
        self._func = func

    def run(self, executor, value):
        raise NotImplementedError


class ShortcutAction(ActionBase):
    def __init__(self, modifiers, key, func=None):
        super(ShortcutAction, self).__init__(modifiers, key, func)

    def run(self, executor, value):
        keys = self._key
        if self._func:
            keys = self._func(self._key, value)
        executor.execute_key(keys, self._modifiers)


class ShortcutValueAction(ActionBase):
    def __init__(self, modifiers, key, func=None):
        super(ShortcutValueAction, self).__init__(modifiers, key, func)

    def run(self, executor, value):
        if self._func:
            value = self._func(value)
        executor.execute_key_value(self._key, self._modifiers, value)


class ShortcutActionSequence(object):
    def __init__(self):
        self._sequence = []

    def add(self, shortcut_action):
        self._sequence.append(shortcut_action)
        return self

    def run(self, executor, value):
        for a in self._sequence:
            a.run(executor, value)

# ---------------------------------------------------------------------------

NO_MOD = (False, False, False)
C_A = (True, True, False)
# C_S = (True, False, True)
C_A_S = (True, True, True)


def _shift(v, resolution):
    midi_max = 127
    dt_range = midi_max / resolution
    return v / resolution - dt_range / 2.0


# MIDI to keyboard event mapping
# Dict key: (MIDI channel, message type, data byte 1)
# Dict value: (Program filter, ShortcutAction or sequence)
SHORTCUT_MAP = {
    (0, CTRL,  0): ('Darktable', ShortcutValueAction(C_A, 'a', lambda v: _shift(v, 25.0))),
    (0, CTRL, 16): ('Darktable', ShortcutValueAction(C_A, 'b', lambda v: _shift(v, 1000.0))),
    (0, CTRL, 64): ('Darktable', ShortcutAction(C_A_S, 'a')),
    (0, CTRL, 48): ('Darktable', ShortcutAction(C_A_S, 'b')),
    (0, CTRL, 32): ('Darktable', ShortcutAction(C_A, 'c')),
    (0, CTRL,  1): ('Darktable', ShortcutValueAction(C_A, 'e', lambda v: v * 40 + 3000)),
    (0, CTRL, 65): ('Darktable', ShortcutAction(C_A_S, 'e')),
    (0, CTRL, 17): ('Darktable', ShortcutValueAction(C_A, 'f', lambda v: v / 10.0)),
    (0, CTRL, 49): ('Darktable', ShortcutAction(C_A_S, 'f')),
    (0, CTRL,  2): ('Darktable', ShortcutValueAction(C_A, 'g', lambda v: _shift(v, 1))),
    (0, CTRL, 18): ('Darktable', ShortcutValueAction(C_A_S, 'g', lambda v: _shift(v, 1))),
    (0, CTRL,  3): ('Darktable', ShortcutValueAction(C_A, 'h', lambda v: _shift(v, 1))),
    (0, CTRL, 19): ('Darktable', ShortcutValueAction(C_A_S, 'h', lambda v: _shift(v, 1))),
    (0, CTRL, 34): ('Darktable', ShortcutAction(C_A, 'i')),
    (0, CTRL, 33): ('Darktable', ShortcutAction(C_A_S, 'j')),
    (0, NOTEON, 36): ('GIMP', ShortcutAction(NO_MOD, 'o')),
    (0, NOTEON, 37): ('GIMP', ShortcutAction(NO_MOD, 'p')),
    (0, NOTEON, 38): ('GIMP', ShortcutAction(NO_MOD, 'a')),
    #(0, CTRL,  0): ('GIMP', ShortcutActionSequence().add(ShortcutAction(C_A, 'b')).add(ShortcutAction(NO_MOD, ']', lambda k, v: k * v))),
}


class EventThread(threading.Thread):
    """
    Background thread that periodically grabs waiting MIDI events from a queue
    and turns them into key shortcuts.
    """
    def __init__(self, events, lock, stop, config_file):
        super(EventThread, self).__init__()
        self._executor = XteExecutor()
        self._wm = XorgWindowManager()
        self._events = events
        self._lock = lock
        self._stop = stop
        logging.debug('EventThread: events %d lock %d stop %d' % (
                      id(self._events), id(self._lock), id(self._stop)))

        # If config file is given, load key mapping
        if config_file:
            pass  # TODO

    def midi_to_keypress(self, midi_type, ctrl, value):
        """Turn a MIDI event into a shortcut through mapping"""
        try:
            name, action = SHORTCUT_MAP[(0, midi_type, ctrl)]
            logging.debug('Found shortcut %s %s' % (name, action))
        except KeyError:
            print 'Could not resolve ctrl %d' % ctrl
        else:
            if name in self._wm.get_active_window_title():
                action.run(self._executor, value)

    def run(self):
        """
        Periodically checks the events queue and copies all MIDI events from it
        in order to turn them into key shortcuts.
        """
        while not self._stop.is_set():
            sleep(0.1)
            #logging.debug('running thread (len events(%d): %d)' % (id(self._events), len(self._events)))
            if not self._events:
                continue

            # Get latest MIDI control events
            self._lock.acquire()
            try:
                list_to_process = self._events.items()
                self._events.clear()
            finally:
                self._lock.release()

            # Process events from copied list and generate keypresses
            for k, midi_data2 in list_to_process:
                midi_type, midi_data1 = k
                self.midi_to_keypress(midi_type, midi_data1, midi_data2)

# ---------------------------------------------------------------------------


class MidiEventProcessor(object):
    """
    Runs the mididings main loop which collects MIDI events, and also manages
    the background thread that processes those events and turns them into key
    shortcuts.
    """
    def __init__(self, config_file=None):
        # Inter-thread communication
        self._events = {}
        self._events_lock = threading.Lock()
        self._stop_processing = threading.Event()
        logging.debug('MidiEventProcessor: events %d lock %d stop %d' % (
                      id(self._events), id(self._events_lock), id(self._stop_processing)))

        # Processor thread (started using threading lib)
        self._processor = EventThread(self._events, self._events_lock, self._stop_processing, config_file)

        # Collector thread (started using mididings)
        self._collector_patch = (Process(self.collect))

    def start(self):
        logging.info('Starting processor thread ...')
        self._processor.start()
        logging.info('Starting collector (mididings) ...')
        run(self._collector_patch)
        logging.info('mididings finished.')
        self._stop_processing.set()
        self._processor.join()
        logging.info('Processing thread joined.')

    def _collect(self, midi):
        if midi.data1 in self._events:
            logging.debug('collect: overwriting events(%d)[%d] with %d' % (id(self._events), midi.data1, midi.data2))
        else:
            logging.debug('collect: new events(%d)[%d] = %d' % (id(self._events), midi.data1, midi.data2))
        self._events[(midi.type, midi.data1)] = midi.data2

    def collect(self, midi):
        # Overwrite earlier events of same CC#
        self._events_lock.acquire()
        try:
            self._collect(midi)
        finally:
            self._events_lock.release()


if __name__ == '__main__':
    proc = MidiEventProcessor()
    print 'Starting up ' + sys.argv[0] + ' ...'
    print 'Use the Jack GUI to set MIDI connections.'
    proc.start()
