"""SCPI laboratory power supply GUI with recording and automation.

Requires: pip install pyserial pillow  (Pillow optional for switch/PNG)
Graph history is prepared in a background thread; Tk widgets remain on the UI thread.
Graph lanes show the latest numeric reading in a right-hand gutter.
Errors are written to psu_control_gui.log beside the script.
SCPI replies are type-checked. One request is read at a time, with a configurable timeout.
Serial settings, slider scales and automation rules are kept in one psu_control_gui.json.
SOUR:*:RAW? readings are labeled DAC (setpoint raw) as in PSU firmware protocol.
Audible alarms use a self-generated WAV, not Windows system event sounds.
"""

import array
import io
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import sys
import wave
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import serial
from serial.tools import list_ports

# Pillow provides antialiased switch artwork. The rest of the GUI still works
# without it (with a simpler native Tk Canvas drawing instead).
try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError:
    Image = ImageDraw = ImageTk = None

DEFAULT_PORT = 'COM4'
DEFAULT_BAUDRATE = 9600
CONFIG_FILE = Path(__file__).resolve().with_name('psu_control_gui.json')
DEFAULT_VOLTAGE_SCALE = 30.0   # Initial slider range, not a limit on commands
DEFAULT_CURRENT_SCALE = 3.0   # Sliders grow if a setpoint exceeds their range
DEFAULT_RESPONSE_TIMEOUT = 2.0
POLL_SECONDS = 0.1  # Pause between completed query rounds; UART throughput sets the actual rate.
BG = '#101827'
PANEL = '#1e293b'
LOG_FILE = Path(__file__).resolve().with_name('psu_control_gui.log')


def create_logger():
    """Keep diagnostic tracebacks for .pyw, which does not have a console."""
    logger = logging.getLogger('psu_control_gui')
    logger.setLevel(logging.WARNING)
    if not logger.handlers:
        try:
            handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000,
                                          backupCount=2, encoding='utf-8')
            handler.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)s %(threadName)s: %(message)s'))
        except OSError:
            handler = logging.NullHandler()
        logger.addHandler(handler)
    return logger


LOGGER = create_logger()


def read_configuration():
    """Read the single JSON configuration or return its defaults."""
    if CONFIG_FILE.exists():
        with CONFIG_FILE.open('r', encoding='utf-8') as source:
            data = json.load(source)
        if not isinstance(data, dict):
            raise ValueError('Configuration must be a JSON object')
        return data
    return {
        'version': 1,
        'serial': {'port': DEFAULT_PORT, 'baudrate': DEFAULT_BAUDRATE,
                   'timeout': DEFAULT_RESPONSE_TIMEOUT},
        'controls': {'voltage_scale': DEFAULT_VOLTAGE_SCALE,
                     'current_scale': DEFAULT_CURRENT_SCALE},
        'automation': {'rules': []},
    }


def write_configuration(data):
    """Atomic replacement keeps a valid previous config if writing fails."""
    temp = CONFIG_FILE.with_suffix(CONFIG_FILE.suffix + '.tmp')
    try:
        with temp.open('w', encoding='utf-8') as output:
            json.dump(data, output, ensure_ascii=False, indent=2)
            output.write('\n')
        temp.replace(CONFIG_FILE)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def load_settings():
    try:
        data = read_configuration()
        serial_data = data.get('serial', {})
        control_data = data.get('controls', {})
        port = str(serial_data.get('port', DEFAULT_PORT)).strip() or DEFAULT_PORT
        baudrate = int(serial_data.get('baudrate', DEFAULT_BAUDRATE))
        timeout = float(serial_data.get('timeout', DEFAULT_RESPONSE_TIMEOUT))
        voltage_scale = float(control_data.get('voltage_scale', DEFAULT_VOLTAGE_SCALE))
        current_scale = float(control_data.get('current_scale', DEFAULT_CURRENT_SCALE))
        if (baudrate <= 0 or not all(math.isfinite(v) and v > 0
                                    for v in (timeout, voltage_scale, current_scale))):
            raise ValueError('Invalid serial or slider settings')
        return port, baudrate, timeout, voltage_scale, current_scale
    except (OSError, ValueError, TypeError, KeyError) as exc:
        LOGGER.warning('Settings fallback: %s', exc)
        return (DEFAULT_PORT, DEFAULT_BAUDRATE, DEFAULT_RESPONSE_TIMEOUT,
                DEFAULT_VOLTAGE_SCALE, DEFAULT_CURRENT_SCALE)


def save_settings(port, baudrate, timeout, voltage_scale, current_scale):
    data = read_configuration()
    data['serial'] = {'port': port, 'baudrate': baudrate, 'timeout': timeout}
    data['controls'] = {'voltage_scale': voltage_scale,
                        'current_scale': current_scale}
    data.setdefault('version', 1)
    write_configuration(data)


# Windows MessageBeep may succeed while the sound event itself is configured
# as "None". Play a generated WAV through the normal audio output instead.
def build_alarm_wav():
    """Generate a short two-tone, 16-bit PCM WAV entirely in memory."""
    sample_rate = 22050
    samples = array.array('h')
    for frequency, seconds in ((880, 0.18), (0, 0.09), (1175, 0.24)):
        count = round(sample_rate * seconds)
        fade_length = max(1, round(sample_rate * 0.008))
        for n in range(count):
            if frequency == 0:
                samples.append(0)
                continue
            envelope = min(1.0, n / fade_length, (count - 1 - n) / fade_length)
            samples.append(int(11500 * envelope *
                               math.sin(2.0 * math.pi * frequency * n / sample_rate)))
    if sys.byteorder != 'little':
        samples.byteswap()
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(samples.tobytes())
    return stream.getvalue()


ALARM_WAV = build_alarm_wav()
_ALARM_LOCK = threading.Lock()


def play_alert_sound(app=None):
    """Request a real audible alert without blocking the UI or SCPI polling."""
    if sys.platform != 'win32':
        # Non-Windows fallback only. Tk's bell must run on the GUI thread.
        if app is not None:
            app.bell()
        return

    def worker():
        # Multiple rules fired in one cycle should produce one clear alarm,
        # not several competing sound streams.
        if not _ALARM_LOCK.acquire(blocking=False):
            return
        try:
            try:
                import winsound
                winsound.PlaySound(ALARM_WAV, winsound.SND_MEMORY)
            except (OSError, RuntimeError) as exc:
                LOGGER.warning('WAV alert playback failed: %s; trying Beep', exc)
                try:
                    winsound.Beep(880, 250)
                except (OSError, RuntimeError) as fallback_exc:
                    LOGGER.error('Alert sound failed: %s', fallback_exc)
            except ImportError:
                LOGGER.error('winsound unavailable on Windows')
        finally:
            _ALARM_LOCK.release()

    threading.Thread(target=worker, daemon=True, name='PSU alarm audio').start()


class SCPIReplyError(ValueError):
    """A query timed out or received a reply of the wrong type."""


class SerialWorker(threading.Thread):
    # Query replies must arrive in the order the requests are sent.
    # OUTP?/MEAS:MODE? have recognizable reply types, so we ask them first.
    QUERIES = (
        ('out', 'OUTP?'),
        ('mode', 'MEAS:MODE?'),
        ('set_v', 'SOUR:VOLT?'),
        ('set_i', 'SOUR:CURR?'),
        ('v', 'MEAS:VOLT?'),
        ('i', 'MEAS:CURR?'),
        ('p', 'MEAS:POW?'),
        ('e', 'MEAS:ENER?'),
        ('dac_v', 'SOUR:VOLT:RAW?'),
        ('dac_i', 'SOUR:CURR:RAW?'),
        ('raw_v', 'MEAS:VOLT:RAW?'),
        ('raw_i', 'MEAS:CURR:RAW?'),
        # Catch a shifted response stream at the END of the round too.
        ('out_check', 'OUTP?'),
    )

    def __init__(self, port, baudrate, timeout, commands, events, stop):
        super().__init__(daemon=True)
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.commands = commands
        self.events = events
        self.stop = stop

    @staticmethod
    def _line(ser):
        raw = ser.readline()
        # A partial line returned by a timeout must not become a valid number
        # (e.g. b'5.' instead of b'5.000\n').
        if raw and not raw.endswith(b'\n'):
            raise SCPIReplyError('incomplete SCPI response (missing newline)')
        return raw.decode('ascii', errors='replace').strip()

    @staticmethod
    def check_response(key, command, response):
        if not response:
            raise SCPIReplyError(f'{command}: no response before timeout')
        # Optional raw queries may be unsupported on another SCPI supply.
        if response.startswith('ERR:'):
            if key in ('dac_v', 'dac_i', 'raw_v', 'raw_i'):
                return '—'
            raise SCPIReplyError(f'{command}: {response}')
        if key in ('out', 'out_check'):
            if response not in ('0', '1'):
                raise SCPIReplyError(f'{command}: expected 0/1, got {response!r}')
        elif key == 'mode':
            if response.upper() not in ('CV', 'CC', 'OFF'):
                raise SCPIReplyError(f'{command}: unexpected mode {response!r}')
        else:
            try:
                number = float(response)
            except ValueError:
                raise SCPIReplyError(f'{command}: expected number, got {response!r}') from None
            if not math.isfinite(number):
                raise SCPIReplyError(f'{command}: non-finite number {response!r}')
            # Deliberately do NOT restrict voltage, current, power, energy,
            # or raw values: ranges vary between different PSU models.
        return response

    @classmethod
    def query(cls, ser, key, command):
        # Send ONE query, wait for ONE complete line, only then send the next.
        ser.write((command + '\n').encode('ascii'))
        ser.flush()
        return cls.check_response(key, command, cls._line(ser))

    def discard_late_replies(self, ser):
        """Drain stale lines after a timeout; never use IDN as a sync marker.

        Waiting for a quiet receive buffer improves recovery, but arbitrary
        delays cannot be solved perfectly by an untagged line protocol.
        """
        quiet_until = time.monotonic() + 0.7
        deadline = time.monotonic() + max(2.5, self.timeout + 0.7)
        while not self.stop.is_set() and time.monotonic() < deadline:
            waiting = ser.in_waiting
            if waiting:
                ser.read(waiting)
                quiet_until = time.monotonic() + 0.7
            if time.monotonic() >= quiet_until:
                break
            self.stop.wait(0.05)
        ser.reset_input_buffer()

    def run(self):
        try:
            with serial.Serial(self.port, self.baudrate, timeout=self.timeout,
                               write_timeout=max(1.0, self.timeout)) as ser:
                if self.stop.wait(2):
                    return
                ser.reset_input_buffer()
                # IDN is asked once for the header only. It is NOT used for
                # resynchronization or required to follow any fixed pattern.
                ser.write(b'*IDN?\n')
                ser.flush()
                try:
                    device_id = self._line(ser)
                except SCPIReplyError:
                    device_id = ''
                if not device_id or device_id.startswith('ERR:'):
                    device_id = self.port
                    self.discard_late_replies(ser)
                self.events.put(('connected', device_id))
                next_poll = 0.0
                while not self.stop.is_set():
                    try:
                        # Serial output commands do not expect a reply.
                        try:
                            while True:
                                command = self.commands.get_nowait()
                                ser.write((command + '\n').encode('ascii'))
                                ser.flush()
                        except queue.Empty:
                            pass

                        if time.monotonic() >= next_poll:
                            readings = {}
                            for key, command in self.QUERIES:
                                if self.stop.is_set():
                                    break
                                readings[key] = self.query(ser, key, command)
                            if not self.stop.is_set():
                                # Publish the complete round only; a partial
                                # round must not corrupt the displayed fields.
                                self.events.put(('readings', readings))
                            next_poll = time.monotonic() + POLL_SECONDS
                    except SCPIReplyError as error:
                        self.events.put(('query_error', str(error)))
                        self.discard_late_replies(ser)
                        next_poll = time.monotonic() + POLL_SECONDS
                    self.stop.wait(0.03)
        except (serial.SerialException, ValueError, OSError) as error:
            if not self.stop.is_set():
                self.events.put(('error', str(error)))
        finally:
            self.events.put(('disconnected', None))


# Additional monitoring tools: history/graphs and user-armed automation.
import csv
from collections import deque
from datetime import datetime
from tkinter import filedialog

HISTORY_LIMIT = 200_000
HISTORY_FIELDS = ('timestamp', 'elapsed_s', 'voltage_v', 'current_a', 'power_w',
                  'energy_wh', 'set_voltage_v', 'set_current_a', 'output_on', 'mode',
                  'adc_voltage_raw', 'adc_current_raw', 'dac_voltage_raw', 'dac_current_raw')
METRICS = (
    ('v', 'VOLTAGE', 'V', '#22c55e'),
    ('i', 'CURRENT', 'A', '#38bdf8'),
    ('p', 'POWER', 'W', '#f59e0b'),
    ('e', 'ENERGY', 'Wh', '#c084fc'),
)


def _is_finite_number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


class MeasurementHistory:
    """Only complete validated SCPI rounds enter the session history."""
    def __init__(self):
        self.samples = deque(maxlen=HISTORY_LIMIT)
        self.capturing = True
        self.start_monotonic = None
        self.log_file = None
        self.log_writer = None
        self.log_path = None
        self.log_error = None

    @staticmethod
    def csv_row(sample):
        stamp = datetime.fromtimestamp(sample['time']).astimezone().isoformat(timespec='milliseconds')
        return (stamp, f"{sample['elapsed']:.3f}",
                *(str(sample[name]) for name in ('v', 'i', 'p', 'e', 'set_v', 'set_i')),
                int(sample['out']), sample['mode'],
                *(sample[name] for name in ('raw_v', 'raw_i', 'dac_v', 'dac_i')))

    def add(self, response):
        if not self.capturing:
            return
        values = {key: _is_finite_number(response.get(key)) for key in
                  ('v', 'i', 'p', 'e', 'set_v', 'set_i')}
        if any(value is None for value in values.values()):
            return
        now = time.time()
        mono = time.monotonic()
        if self.start_monotonic is None:
            self.start_monotonic = mono
        sample = {**values, 'time': now, 'elapsed': mono - self.start_monotonic,
                  'out': response.get('out') == '1',
                  'mode': str(response.get('mode', '?')),
                  **{name: str(response.get(name, '—')) for name in
                     ('raw_v', 'raw_i', 'dac_v', 'dac_i')}}
        self.samples.append(sample)
        if self.log_writer:
            try:
                self.log_writer.writerow(self.csv_row(sample))
                self.log_file.flush()  # Keep logged data after a sudden stop.
            except OSError as exc:
                self.log_error = str(exc)
                self.stop_logging()

    def clear(self):
        self.samples.clear()
        self.start_monotonic = None

    def export_csv(self, path):
        with open(path, 'w', newline='', encoding='utf-8-sig') as file:
            writer = csv.writer(file)
            writer.writerow(HISTORY_FIELDS)
            for sample in self.samples:
                writer.writerow(self.csv_row(sample))

    def start_logging(self, path):
        self.stop_logging()
        self.log_file = open(path, 'w', newline='', encoding='utf-8-sig')
        self.log_writer = csv.writer(self.log_file)
        self.log_writer.writerow(HISTORY_FIELDS)
        self.log_file.flush()
        self.log_path = path
        self.log_error = None
        self.capturing = True

    def stop_logging(self):
        if self.log_file is not None:
            try:
                self.log_file.close()
            finally:
                self.log_file = None
                self.log_writer = None
                self.log_path = None

    def import_csv(self, path):
        loaded = deque(maxlen=HISTORY_LIMIT)
        with open(path, newline='', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            if not set(HISTORY_FIELDS).issubset(reader.fieldnames or []):
                raise ValueError('This is not a PSU history CSV (missing columns).')
            for row in reader:
                numbers = {key: _is_finite_number(row[col]) for key, col in
                           (('v', 'voltage_v'), ('i', 'current_a'),
                            ('p', 'power_w'), ('e', 'energy_wh'),
                            ('set_v', 'set_voltage_v'), ('set_i', 'set_current_a'))}
                if any(x is None for x in numbers.values()):
                    continue
                stamp = datetime.fromisoformat(row['timestamp']).timestamp()
                elapsed = _is_finite_number(row['elapsed_s'])
                if elapsed is None or not math.isfinite(stamp):
                    continue
                loaded.append({**numbers, 'time': stamp, 'elapsed': elapsed,
                               'out': row['output_on'].strip() in ('1', 'True'),
                               'mode': row['mode'],
                               **{name: row.get(col, '—') for name, col in
                                  (('raw_v', 'adc_voltage_raw'),
                                   ('raw_i', 'adc_current_raw'),
                                   ('dac_v', 'dac_voltage_raw'),
                                   ('dac_i', 'dac_current_raw'))}})
        if not loaded:
            raise ValueError('The file contains no valid measurements.')
        self.stop_logging()
        self.samples = loaded
        self.capturing = False  # Historical files should not silently mix with live data.
        self.start_monotonic = None
        return len(loaded)


class GraphsDialog(tk.Toplevel):
    """Four independent auto-scaled time-series graphs. No matplotlib dependency."""
    WINDOWS = {'1 min': 60, '5 min': 300, '15 min': 900,
               '1 hour': 3600, 'All': None}

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.history = app.history
        self.title('PSU • Graphs & recording')
        self.configure(bg=BG)
        self.geometry('1050x740')
        self.minsize(830, 450)
        self.view = tk.StringVar(value='5 min')
        self.enabled = {key: tk.BooleanVar(value=True) for key, *_ in METRICS}
        self.info = tk.StringVar()
        self._refresh_job = None
        self._redraw_job = None
        self._last_draw_at = 0.0
        # Data preparation is CPU-heavy for long recordings. Do it in a worker,
        # never in the Tk event loop that also updates the main PSU monitor.
        # Worker input/output contain plain Python data only; Tk stays on this thread.
        self._render_tasks = queue.Queue(maxsize=1)
        self._render_results = queue.Queue(maxsize=1)
        self._render_stop = threading.Event()
        self._render_version = 0
        self._render_pending = False
        self._result_job = None
        self._build()
        self._render_thread = threading.Thread(target=self._plot_worker,
                                               name='PSU graph preparation', daemon=True)
        self._render_thread.start()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self._result_job = self.after(75, self._collect_scenes)
        self._refresh()

    def _button(self, parent, text, command, color='#334155'):
        button = tk.Button(parent, text=text, command=command, bg=color,
                           fg='#f8fafc', activebackground='#475569',
                           activeforeground='white', relief='flat', bd=0,
                           padx=10, pady=5, font=('Segoe UI', 10))
        button.pack(side='left', padx=(0, 6))
        return button

    def _build(self):
        toolbar = tk.Frame(self, bg=BG)
        toolbar.pack(fill='x', padx=14, pady=(12, 3))
        self.capture_button = self._button(toolbar, '', self.toggle_capture, '#2563eb')
        self._button(toolbar, 'Clear', self.clear)
        self._button(toolbar, 'Save CSV', self.save_csv)
        self._button(toolbar, 'Open CSV', self.load_csv)
        self.log_button = self._button(toolbar, 'Log to CSV…', self.toggle_logging)
        self.png_button = self._button(toolbar, 'Save PNG', self.save_png)
        if Image is None:
            self.png_button.configure(state='disabled')
        self.app.label(toolbar, 'View:', 10).pack(side='left', padx=(15, 5))
        view_selector = ttk.Combobox(toolbar, textvariable=self.view,
                                     state='readonly', width=8,
                                     values=list(self.WINDOWS))
        view_selector.pack(side='left')
        # Use the selection event rather than an in-variable Tcl write trace.
        # Work is queued after the combobox interaction has finished.
        view_selector.bind('<<ComboboxSelected>>', lambda _event: self.request_redraw())

        filters = tk.Frame(self, bg=BG)
        filters.pack(fill='x', padx=17, pady=(4, 3))
        for key, title, _, color in METRICS:
            tk.Checkbutton(filters, text=title, variable=self.enabled[key],
                           bg=BG, fg=color, activebackground=BG,
                           activeforeground=color, selectcolor=PANEL,
                           font=('Segoe UI', 10), command=self.request_redraw).pack(side='left', padx=(0, 14))
        self.canvas = tk.Canvas(self, bg=PANEL, bd=0, highlightthickness=0)
        self.canvas.pack(fill='both', expand=True, padx=16, pady=(5, 4))
        self.app.label(self, textvariable=self.info, color='#94a3b8', size=10,
                       anchor='w').pack(fill='x', padx=17, pady=(1, 10))
        self.canvas.bind('<Configure>', lambda _event: self.request_redraw())

    def request_redraw(self):
        """Coalesce rapid View/filter/resize events into one canvas redraw."""
        if self._redraw_job is not None:
            try:
                self.after_cancel(self._redraw_job)
            except tk.TclError:
                pass
        self._redraw_job = self.after(75, self._requested_draw)

    def _requested_draw(self):
        self._redraw_job = None
        self.draw()

    def _refresh(self):
        if not self.winfo_exists():
            return
        # Schedule the NEXT tick before drawing.  A failure or slow render
        # must not permanently stop the graph's update loop.
        self._refresh_job = self.after(500, self._refresh)
        try:
            self.capture_button.config(text='Pause capture' if self.history.capturing else 'Resume capture')
            self.log_button.config(text='Stop logging' if self.history.log_file else 'Log to CSV…')
            count = len(self.history.samples)
            status = 'LIVE' if self.history.capturing else 'PAUSED'
            log = f' • logging: {Path(self.history.log_path).name}' if self.history.log_path else ''
            if self.history.log_error:
                log += f' • CSV ERROR: {self.history.log_error}'
            stamp = ''
            if count:
                stamp = f' • latest: {datetime.fromtimestamp(self.history.samples[-1]["time"]):%H:%M:%S}'
            self.info.set(f'{status} • {count:,} samples (memory limit {HISTORY_LIMIT:,}){stamp}{log} • '
                          'CSV includes timestamps, measured values, setpoints, output and mode')
            # A full recording can be expensive to draw.  Update the status
            # every 500 ms, while keeping the plot itself responsive.
            interval = 2.0 if (self.view.get() == 'All' and count > 30_000) else 0.5
            if time.monotonic() - self._last_draw_at >= interval:
                self.draw(force=False)
        except Exception as exc:
            # The graph must never take down the main PSU display.
            LOGGER.exception('Graph refresh failed')
            self.info.set(f'Graph refresh error: {type(exc).__name__}: {exc}')

    def toggle_capture(self):
        self.history.capturing = not self.history.capturing
        if not self.history.capturing and self.history.log_file:
            self.history.stop_logging()

    def clear(self):
        if self.history.samples and messagebox.askyesno('Clear graphs',
                'Clear the in-memory history?\nAny running CSV log will remain on disk.',
                parent=self):
            self.history.clear()
            self.draw()

    def save_csv(self):
        if not self.history.samples:
            messagebox.showinfo('No data', 'No measurements recorded yet.', parent=self)
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension='.csv',
                                           filetypes=[('CSV files', '*.csv')],
                                           initialfile='psu_measurements.csv')
        if path:
            try:
                self.history.export_csv(path)
            except OSError as exc:
                messagebox.showerror('Save failed', str(exc), parent=self)

    def load_csv(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[('CSV files', '*.csv')])
        if not path:
            return
        if not messagebox.askyesno('Open recorded measurements',
                'Replace the in-memory history with this CSV and pause live capture?',
                parent=self):
            return
        try:
            n = self.history.import_csv(path)
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror('Open failed', str(exc), parent=self)
        else:
            self.view.set('All')
            self.info.set(f'Loaded {n} readings from {Path(path).name}')
            self.draw()

    def toggle_logging(self):
        if self.history.log_file:
            self.history.stop_logging()
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension='.csv',
                                           filetypes=[('CSV files', '*.csv')],
                                           initialfile='psu_live_log.csv')
        if path:
            try:
                self.history.start_logging(path)
            except OSError as exc:
                messagebox.showerror('Log failed', str(exc), parent=self)

    def _plot_scene(self, width, height):
        """Build a vector scene (used synchronously only for explicit PNG export)."""
        visible = tuple(metric for metric in METRICS if self.enabled[metric[0]].get())
        window = self.WINDOWS.get(self.view.get(), 300)
        return self._plot_scene_data(tuple(self.history.samples), visible,
                                     window, width, height)

    @staticmethod
    def _plot_scene_data(data, visible, window, width, height):
        """Prepare graph paths from a snapshot; NO Tkinter calls are allowed here."""
        instructions = []
        if not data or not visible:
            return [('text', width / 2, height / 2,
                     'No measurements to display', '#94a3b8', 'center', 16)]

        latest = data[-1]['time']
        start = latest - window if window is not None else data[0]['time']
        data = [item for item in data if item['time'] >= start]
        if not data:
            return instructions
        earliest = latest - window if window is not None else data[0]['time']
        x1, x2 = 85, width - 140  # right gutter for latest value in each lane
        top, bottom = 15, height - 36
        area_h = max(20, (bottom - top) / len(visible))
        dx = max(0.001, latest - earliest)

        for n, (key, name, unit, color) in enumerate(visible):
            lane_top = top + n * area_h
            lane_bottom = lane_top + area_h - 24
            vals = [record[key] for record in data]
            low, high = min(vals), max(vals)
            pad = (max(0.001, abs(high) * 0.05) if abs(high - low) < 1e-12
                   else (high - low) * 0.08)
            low -= pad
            high += pad
            plot_top = lane_top + 29
            lane_height = max(3, lane_bottom - plot_top - 2)
            instructions.append(('text', x1 + 12, lane_top + 5,
                                 f'{name} ({unit})', color, 'left', 12))
            # Display the actual last sample, not the axis maximum or a rounded tick.
            # This appears in PNG export too, because both use the same scene.
            instructions.append(('text', x2 + 15, lane_top + 36,
                                 f'{vals[-1]:.3f} {unit}', color, 'left', 13))
            instructions.append(('text', x1 - 8, plot_top, f'{high:.3f}',
                                 '#94a3b8', 'right', 10))
            instructions.append(('text', x1 - 8, lane_bottom - 3, f'{low:.3f}',
                                 '#94a3b8', 'right', 10))
            for frac in (0, 0.25, 0.5, 0.75, 1):
                y = plot_top + lane_height * frac
                instructions.append(('line', (x1, y, x2, y), '#334155', 1))

            # Each pixel column keeps FIRST, MIN, MAX and LAST points. Preserve
            # brief spikes without holding all N points in nested Tk objects.
            buckets = {}
            for idx, record in enumerate(data):
                x = x1 + (record['time'] - earliest) / dx * (x2 - x1)
                y = plot_top + (high - record[key]) / (high - low) * lane_height
                item = (idx, x, y)
                column = int(x)
                bucket = buckets.get(column)
                if bucket is None:
                    buckets[column] = [item, item, item, item]
                else:
                    if y < bucket[1][2]:
                        bucket[1] = item
                    if y > bucket[2][2]:
                        bucket[2] = item
                    bucket[3] = item
            coords = []
            for column in sorted(buckets):
                unique = {item[0]: item for item in buckets[column]}
                for _, x, y in sorted(unique.values(), key=lambda item: item[0]):
                    coords.extend((x, y))
            if len(coords) >= 4:
                instructions.append(('line', tuple(coords), color, 2))
            elif coords:
                instructions.append(('circle', coords[0], coords[1], 2, color))

        for fraction in (0, .25, .5, .75, 1):
            x = x1 + fraction * (x2 - x1)
            stamp = datetime.fromtimestamp(earliest + fraction * dx)
            fmt = '%H:%M:%S' if dx < 3600 else '%d %b %H:%M'
            instructions.append(('text', x, height - 24, stamp.strftime(fmt),
                                 '#94a3b8', 'center', 10))
        return instructions

    @staticmethod
    def _offer_latest(q, value):
        """Coalesce obsolete frames, so changing View cannot pile up renders."""
        try:
            q.put_nowait(value)
        except queue.Full:
            try:
                q.get_nowait()
            except queue.Empty:
                pass
            q.put_nowait(value)

    def _plot_worker(self):
        while not self._render_stop.is_set():
            try:
                version, data, visible, window, width, height = self._render_tasks.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                scene = self._plot_scene_data(data, visible, window, width, height)
                error = None
            except Exception as exc:
                LOGGER.exception('Graph data preparation failed')
                scene = None
                error = f'{type(exc).__name__}: {exc}'
            if not self._render_stop.is_set():
                self._offer_latest(self._render_results, (version, scene, error))

    def draw(self, force=True):
        """Queue a snapshot; don't starve slow computers with endless new jobs."""
        if not self.winfo_exists():
            return
        # Periodic refreshes never supersede an in-flight refresh. A View or
        # filter change (force=True) can supersede it to display the new range.
        if self._render_pending and not force:
            return
        self._last_draw_at = time.monotonic()
        self._render_pending = True
        self._render_version += 1
        job = (self._render_version, tuple(self.history.samples),
               tuple(metric for metric in METRICS if self.enabled[metric[0]].get()),
               self.WINDOWS.get(self.view.get(), 300),
               max(200, self.canvas.winfo_width()),
               max(100, self.canvas.winfo_height()))
        self._offer_latest(self._render_tasks, job)

    def _collect_scenes(self):
        """Only this Tk thread touches the Canvas, with already-bounded paths."""
        self._result_job = None
        try:
            while True:
                version, scene, error = self._render_results.get_nowait()
                if version != self._render_version:
                    continue
                self._render_pending = False
                if error:
                    self.info.set('Graph error: ' + error)
                else:
                    self._paint_scene(scene)
        except queue.Empty:
            pass
        except Exception as exc:
            LOGGER.exception('Graph Canvas update failed')
            self.info.set(f'Graph drawing error: {type(exc).__name__}: {exc}')
        finally:
            if self.winfo_exists():
                self._result_job = self.after(75, self._collect_scenes)

    def _paint_scene(self, scene):
        cv = self.canvas
        cv.delete('all')
        for item in scene:
            if item[0] == 'line':
                _, coords, color, thickness = item
                cv.create_line(*coords, fill=color, width=thickness)
            elif item[0] == 'text':
                _, x, y, msg, color, align, size = item
                cv.create_text(x, y, text=msg, fill=color,
                               font=('Segoe UI', size),
                               anchor={'left': 'nw', 'right': 'ne', 'center': 'center'}[align])
            elif item[0] == 'circle':
                _, x, y, radius, color = item
                cv.create_oval(x-radius, y-radius, x+radius, y+radius,
                               fill=color, outline=color)

    def save_png(self):
        if Image is None:
            messagebox.showerror('Pillow missing', 'Install pillow for PNG export.', parent=self)
            return
        if not self.history.samples:
            messagebox.showinfo('No data', 'No measurements recorded yet.', parent=self)
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension='.png',
                                           filetypes=[('PNG files', '*.png')],
                                           initialfile='psu_graphs.png')
        if not path:
            return
        # Draw directly to a file, not a screen capture (works even if occluded).
        from PIL import ImageFont
        w, h, scale = max(800, self.canvas.winfo_width()), max(500, self.canvas.winfo_height()), 2
        image = Image.new('RGB', (w * scale, h * scale), PANEL)
        drawer = ImageDraw.Draw(image)
        fonts = {}
        for item in self._plot_scene(w, h):
            if item[0] == 'line':
                _, coords, color, thickness = item
                drawer.line([(round(coords[i]*scale), round(coords[i+1]*scale))
                             for i in range(0, len(coords), 2)],
                            fill=color, width=thickness*scale)
            elif item[0] == 'circle':
                _, x, y, radius, color = item
                drawer.ellipse((round((x-radius)*scale), round((y-radius)*scale),
                                round((x+radius)*scale), round((y+radius)*scale)), fill=color)
            elif item[0] == 'text':
                _, x, y, msg, color, align, size = item
                if size not in fonts:
                    font = None
                    for family in ('segoeui.ttf', 'DejaVuSans.ttf'):
                        try:
                            font = ImageFont.truetype(family, size*scale)
                            break
                        except OSError:
                            continue
                    fonts[size] = font or ImageFont.load_default()
                drawer.text((round(x*scale), round(y*scale)), msg, fill=color,
                            font=fonts[size],
                            anchor={'left': 'lt', 'right': 'rt', 'center': 'mm'}[align])
        try:
            image.save(path)
        except OSError as exc:
            messagebox.showerror('Save failed', str(exc), parent=self)

    def close(self):
        self._render_stop.set()
        for job in (self._refresh_job, self._redraw_job, self._result_job):
            if job is not None:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
        self.app.graphs_dialog = None
        self.destroy()


SIGNALS = {'Voltage': 'v', 'Current': 'i', 'Power': 'p', 'Energy': 'e'}


def describe_condition(cond):
    return f"{cond['signal']} {cond['op']} {cond['threshold']}"


def describe_rule(rule):
    condition = describe_condition(rule['a'])
    if rule['b']:
        condition += f" {rule['combine']} {describe_condition(rule['b'])}"
    actions = []
    if rule['beep']:
        actions.append('Beep')
    if rule['output'] != 'Keep':
        actions.append(f"OUTPUT {rule['output']}")
    if rule['change_v']:
        actions.append(f"Set V={float(rule['target_v']):g}")
    if rule['change_i']:
        actions.append(f"Set I={float(rule['target_i']):g}")
    return condition + ' → ' + ', '.join(actions)


def valid_rule(rule):
    """Validate user-edited and file-loaded rules before allowing commands."""
    def check_cond(cond):
        if not isinstance(cond, dict) or cond.get('signal') not in SIGNALS or cond.get('op') not in ('>=', '<='):
            raise ValueError('Invalid comparison')
        if _is_finite_number(cond.get('threshold')) is None:
            raise ValueError('Invalid numeric threshold')
    check_cond(rule['a'])
    if rule['b']:
        check_cond(rule['b'])
    if rule['combine'] not in ('AND', 'OR') or rule['output'] not in ('Keep', 'ON', 'OFF'):
        raise ValueError('Invalid rule action or logical operator')
    if not (rule['beep'] or rule['output'] != 'Keep' or rule['change_v'] or rule['change_i']):
        raise ValueError('Select at least one action')
    for key, target in (('change_v', 'target_v'), ('change_i', 'target_i')):
        if rule[key] and _is_finite_number(rule[target]) is None:
            raise ValueError('Invalid target setpoint')
    if not str(rule['name']).strip():
        raise ValueError('Rule needs a name')
    return rule


class AutomationEngine:
    """Edge-triggered, explicitly armed user automation. Never opens UART itself."""
    def __init__(self, app):
        self.app = app
        self.rules = []
        self.armed = False
        self.logs = deque(maxlen=70)
        self.load()

    def load(self):
        try:
            content = read_configuration().get('automation', {}).get('rules', [])
            if isinstance(content, list):
                for source_rule in content:
                    try:
                        rule = dict(source_rule)
                        valid_rule(rule)
                        rule['enabled'] = bool(rule.get('enabled', True))
                        rule['once'] = bool(rule.get('once', True))
                        self.rules.append(rule)
                    except (ValueError, KeyError, TypeError, AttributeError) as exc:
                        LOGGER.warning('Skipping invalid automation rule: %s', exc)
        except (OSError, ValueError, TypeError) as exc:
            LOGGER.warning('Cannot load automation rules: %s', exc)
        self._reset_runtime()

    def save(self):
        data = read_configuration()
        data['automation'] = {'rules': self.rules}
        data.setdefault('version', 1)
        write_configuration(data)

    def _reset_runtime(self):
        self.runtime = [{'active': False, 'clear_samples': 0,
                         'fired': False, 'hits': 0} for _ in self.rules]

    def disarm(self, reason='Stopped'):
        if self.armed:
            self.logs.appendleft(f'{datetime.now():%H:%M:%S}  {reason}')
        self.armed = False
        self._notify()

    def arm(self):
        self._reset_runtime()
        self.armed = True
        self.logs.appendleft(f'{datetime.now():%H:%M:%S}  Armed')
        self._notify()

    @staticmethod
    def _matches(cond, data):
        val = _is_finite_number(data.get(SIGNALS[cond['signal']]))
        limit = _is_finite_number(cond['threshold'])
        if val is None or limit is None:
            return False
        return val >= limit if cond['op'] == '>=' else val <= limit

    def observe(self, data):
        if not self.armed or not self.app.connected:
            return
        triggered = False
        for index, rule in enumerate(self.rules):
            if not rule['enabled']:
                continue
            state = self.runtime[index]
            a = self._matches(rule['a'], data)
            b = self._matches(rule['b'], data) if rule['b'] else True
            matches = a and b if rule['combine'] == 'AND' else (a or b if rule['b'] else a)
            if not matches:
                state['clear_samples'] += 1
                if state['clear_samples'] >= 2:
                    state['active'] = False
                continue
            state['clear_samples'] = 0
            if state['active'] or (rule['once'] and state['fired']):
                continue
            state['active'] = True
            state['fired'] = True
            state['hits'] += 1
            triggered = True
            if rule['output'] != 'Keep':
                self.app.commands.put('OUTP ' + ('1' if rule['output'] == 'ON' else '0'))
            if rule['change_v']:
                self.app.commands.put(f"SOUR:VOLT {float(rule['target_v']):.3f}")
                self.app.controls['set_v']['pending'] = None
            if rule['change_i']:
                self.app.commands.put(f"SOUR:CURR {float(rule['target_i']):.3f}")
                self.app.controls['set_i']['pending'] = None
            if rule['beep']:
                play_alert_sound(self.app)
            self.logs.appendleft(f"{datetime.now():%H:%M:%S}  {rule['name']}: {describe_rule(rule)}")
        if triggered:
            self._notify()

    def _notify(self):
        if getattr(self.app, 'automation_dialog', None):
            self.app.automation_dialog.refresh()
        if hasattr(self.app, 'automation_button'):
            self.app.automation_button.configure(
                bg='#854d0e' if self.armed else '#334155')


class IconTooltip:
    """Small non-focusable tooltip for icon-only title-bar buttons."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.pop = None
        self.job = None
        widget.bind('<Enter>', self._enter, add='+')
        widget.bind('<Leave>', self._leave, add='+')
        widget.bind('<ButtonPress>', self._leave, add='+')

    def _enter(self, _event):
        self._leave()
        self.job = self.widget.after(500, self._show)

    def _show(self):
        self.job = None
        if not self.widget.winfo_exists() or self.pop is not None:
            return
        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.pop = tk.Toplevel(self.widget)
        self.pop.overrideredirect(True)
        tk.Label(self.pop, text=self.text, bg='#334155', fg='#f8fafc',
                 padx=8, pady=4, font=('Segoe UI', 9)).pack()
        self.pop.geometry(f'+{x}+{y}')

    def _leave(self, _event=None):
        if self.job is not None:
            self.widget.after_cancel(self.job)
            self.job = None
        if self.pop is not None:
            self.pop.destroy()
            self.pop = None


class AutomationDialog(tk.Toplevel):
    """Rules and their editor in one window (no nested modal dialog)."""
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.engine = app.automation
        self.title('PSU • Automation')
        self.configure(bg=BG)
        self.geometry('1030x655')
        self.minsize(880, 590)
        self._editor_index = None
        self._arm_images = {}
        self._build()
        self.refresh()
        if self.engine.rules:
            self._select_index(0, load=True)
        else:
            self._load_rule(None)
        self.protocol('WM_DELETE_WINDOW', self.close)

    def _btn(self, parent, text, handler, color='#334155'):
        return tk.Button(parent, text=text, command=handler, bg=color,
                         fg='#f8fafc', activebackground='#475569',
                         activeforeground='white', relief='flat', bd=0,
                         padx=12, pady=6, font=('Segoe UI', 10))

    @staticmethod
    def _text(parent, title, size=10, color='#cbd5e1'):
        return tk.Label(parent, text=title, bg=parent.cget('bg'), fg=color,
                        font=('Segoe UI', size))

    @staticmethod
    def _entry(parent, var, width=12):
        return tk.Entry(parent, textvariable=var, width=width,
                        bg='#334155', fg='#f8fafc', insertbackground='white',
                        relief='flat', highlightthickness=0,
                        font=('Segoe UI', 10))

    @staticmethod
    def _check(parent, text, var):
        return tk.Checkbutton(parent, text=text, variable=var,
                              bg=PANEL, fg='#e2e8f0', selectcolor='#334155',
                              activebackground=PANEL, activeforeground='white',
                              font=('Segoe UI', 10))

    @staticmethod
    def _combo(parent, var, options, width=12):
        return ttk.Combobox(parent, textvariable=var, values=options,
                            width=width, state='readonly')

    def _condition_row(self, parent, row, label):
        self._text(parent, label).grid(row=row, column=0, sticky='w', pady=5)
        sig = tk.StringVar(value='Voltage')
        op = tk.StringVar(value='>=')
        val = tk.StringVar(value='5.0')
        self._combo(parent, sig, tuple(SIGNALS), 11).grid(row=row, column=1, padx=3, sticky='ew')
        self._combo(parent, op, ('>=', '<='), 5).grid(row=row, column=2, padx=3)
        self._entry(parent, val, 12).grid(row=row, column=3, padx=3, sticky='ew')
        return (sig, op, val)

    def _build(self):
        header = tk.Frame(self, bg=BG)
        header.pack(fill='x', padx=16, pady=(12, 10))
        self.state_label = self._text(header, '', 12, '#94a3b8')
        self.state_label.pack(side='left')
        self.arm_switch = tk.Canvas(header, width=88, height=36, bg=BG,
                                    highlightthickness=0, bd=0, relief='flat',
                                    takefocus=0, cursor='hand2')
        self.arm_switch.pack(side='right', padx=(8, 0))
        self.arm_switch.bind('<Button-1>', self.toggle_arm)
        self._text(header, 'AUTOMATION', 10, '#cbd5e1').pack(side='right')

        body = tk.Frame(self, bg=BG)
        body.pack(fill='both', expand=True, padx=16)
        body.grid_columnconfigure(0, weight=2, minsize=285)
        body.grid_columnconfigure(1, weight=4, minsize=530)
        body.grid_rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=PANEL, padx=10, pady=10)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 6))
        self._text(left, 'RULES', 12, '#e2e8f0').pack(anchor='w', pady=(0, 8))
        list_container = tk.Frame(left, bg=PANEL)
        list_container.pack(fill='both', expand=True)
        self.listbox = tk.Listbox(list_container, bg='#172132', fg='#e2e8f0',
                                  selectbackground='#1d4ed8', selectforeground='white',
                                  font=('Segoe UI', 10), activestyle='none',
                                  relief='flat', exportselection=False, height=11)
        scrollbar = tk.Scrollbar(list_container, orient='vertical',
                                 command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.listbox.pack(side='left', fill='both', expand=True)
        self.listbox.bind('<<ListboxSelect>>', self._on_select)
        left_controls = tk.Frame(left, bg=PANEL)
        left_controls.pack(fill='x', pady=(9, 0))
        self._btn(left_controls, 'Remove', self.remove).pack(side='left', padx=(0, 6))
        self._btn(left_controls, 'Enable / Disable', self.toggle_enabled).pack(side='left')
        self._text(left,
                   'Select a rule to edit it. Add creates a new rule;\n'
                   'Update replaces the selected rule.', 9, '#94a3b8').pack(
                       anchor='w', pady=(12, 0))

        editor = tk.Frame(body, bg=PANEL, padx=15, pady=9)
        editor.grid(row=0, column=1, sticky='nsew', padx=(6, 0))
        editor.grid_columnconfigure(1, weight=1)
        editor.grid_columnconfigure(3, weight=1)
        self._text(editor, 'RULE SETTINGS', 12, '#e2e8f0').grid(
            row=0, column=0, columnspan=4, sticky='w', pady=(0, 7))
        self.name = tk.StringVar(value='New rule')
        self.rule_on = tk.BooleanVar(value=True)
        self.once = tk.BooleanVar(value=True)
        self.combine = tk.StringVar(value='AND')
        self.second_on = tk.BooleanVar(value=False)
        self.beep = tk.BooleanVar(value=True)
        self.output = tk.StringVar(value='Keep')
        self.change_v = tk.BooleanVar(value=False)
        self.change_i = tk.BooleanVar(value=False)
        self.target_v = tk.StringVar(value='5.0')
        self.target_i = tk.StringVar(value='0.5')
        self._text(editor, 'Name').grid(row=1, column=0, sticky='w')
        self._entry(editor, self.name, 30).grid(row=1, column=1, columnspan=3,
                                                sticky='ew', padx=(4, 0))
        self._text(editor, 'IF measured value…', 10, '#93c5fd').grid(
            row=2, column=0, columnspan=4, sticky='w', pady=(10, 1))
        self.a = self._condition_row(editor, 3, 'Condition 1')
        self._check(editor, 'Second condition', self.second_on).grid(
            row=4, column=0, columnspan=2, sticky='w', pady=(5, 0))
        self._combo(editor, self.combine, ('AND', 'OR'), 7).grid(row=4, column=2, sticky='w')
        self.b = self._condition_row(editor, 5, 'Condition 2')
        self._text(editor, 'Thresholds are numbers (V / A / W / Wh).', 9,
                   '#94a3b8').grid(row=6, column=0, columnspan=4,
                                    sticky='w', pady=(0, 6))
        ttk.Separator(editor).grid(row=7, column=0, columnspan=4,
                                   sticky='ew', pady=(0, 5))
        self._text(editor, 'THEN perform…', 10, '#93c5fd').grid(
            row=8, column=0, columnspan=4, sticky='w', pady=(0, 2))
        self._check(editor, 'Play sound', self.beep).grid(
            row=9, column=0, columnspan=2, sticky='w')
        self._btn(editor, 'Test sound', lambda: play_alert_sound(self.app)).grid(
            row=9, column=2, columnspan=2, sticky='w', padx=3)
        self._text(editor, 'OUTPUT').grid(row=10, column=0, sticky='w', pady=5)
        self._combo(editor, self.output, ('Keep', 'OFF', 'ON'), 10).grid(
            row=10, column=1, sticky='w')
        self._check(editor, 'Set voltage (V)', self.change_v).grid(
            row=11, column=0, columnspan=2, sticky='w')
        self._entry(editor, self.target_v).grid(row=11, column=2, sticky='w')
        self._check(editor, 'Set current (A)', self.change_i).grid(
            row=12, column=0, columnspan=2, sticky='w')
        self._entry(editor, self.target_i).grid(row=12, column=2, sticky='w')
        self._check(editor, 'One-shot (once per arming)', self.once).grid(
            row=13, column=0, columnspan=4, sticky='w', pady=(7, 0))
        self._check(editor, 'Rule enabled', self.rule_on).grid(
            row=14, column=0, columnspan=4, sticky='w')
        buttons = tk.Frame(editor, bg=PANEL)
        buttons.grid(row=15, column=0, columnspan=4, sticky='ew', pady=(10, 0))
        self.add_button = self._btn(buttons, 'Add new rule', self.add, '#2563eb')
        self.add_button.pack(side='left', padx=(0, 8))
        self.update_button = self._btn(buttons, 'Update selected', self.update)
        self.update_button.pack(side='left')

        events = tk.Frame(self, bg=BG)
        events.pack(fill='x', padx=18, pady=(9, 1))
        self._text(events, 'RECENT EVENTS', 9, '#94a3b8').pack(anchor='w')
        self.log_label = self._text(events, '', 9, '#cbd5e1')
        self.log_label.configure(anchor='w', justify='left', height=2)
        self.log_label.pack(fill='x')
        self._text(self,
                   'Automation never arms on startup; disconnect and *RST disarm it. '
                   'Actions are queued on the existing SCPI connection.',
                   9, '#94a3b8').pack(anchor='w', padx=18, pady=(0, 9))

    def refresh(self):
        """Refresh summaries without overwriting unsaved editor changes."""
        index = self._selected()
        self.listbox.delete(0, 'end')
        for i, rule in enumerate(self.engine.rules):
            hits = self.engine.runtime[i]['hits']
            icon = '✓' if rule['enabled'] else '×'
            self.listbox.insert('end', f" {icon}  {rule['name'][:30]}   [hits: {hits}]")
        if index is not None and index < self.listbox.size():
            self.listbox.selection_set(index)
        armed = self.engine.armed
        self.state_label.config(text='● ARMED' if armed else '○ DISARMED',
                                fg='#fbbf24' if armed else '#94a3b8')
        self.render_arm_switch()
        self.update_button.configure(state='normal' if self._selected() is not None else 'disabled')
        self.log_label.config(text='\n'.join(list(self.engine.logs)[:2]) or 'No events yet')

    def _selected(self):
        indices = self.listbox.curselection()
        return indices[0] if indices else None

    def _select_index(self, index, load=False):
        self.listbox.selection_clear(0, 'end')
        if 0 <= index < self.listbox.size():
            self.listbox.selection_set(index)
            self.listbox.see(index)
            if load:
                self._load_rule(self.engine.rules[index], index)
            self.update_button.configure(state='normal')

    def _on_select(self, _event=None):
        index = self._selected()
        if index is not None and index != self._editor_index:
            self._load_rule(self.engine.rules[index], index)
        self.update_button.configure(state='normal' if index is not None else 'disabled')

    def _load_rule(self, rule=None, index=None):
        """Show the selected rule (or a fresh draft) in the SAME editor panel."""
        old = rule or {}
        self._editor_index = index
        self.name.set(str(old.get('name', 'New rule')))
        self.rule_on.set(bool(old.get('enabled', True)))
        self.once.set(bool(old.get('once', True)))
        self.combine.set(old.get('combine', 'AND'))
        self.second_on.set(bool(old.get('b')))
        self.beep.set(bool(old.get('beep', True)))
        self.output.set(old.get('output', 'Keep'))
        self.change_v.set(bool(old.get('change_v', False)))
        self.change_i.set(bool(old.get('change_i', False)))
        self.target_v.set(str(old.get('target_v', 5.0)))
        self.target_i.set(str(old.get('target_i', 0.5)))
        for controls, source in ((self.a, old.get('a')),
                                 (self.b, old.get('b'))):
            cond = source or {'signal': 'Voltage', 'op': '>=', 'threshold': '5.0'}
            for variable, value in zip(controls,
                                       (cond['signal'], cond['op'], cond['threshold'])):
                variable.set(str(value))

    @staticmethod
    def _make_condition(controls):
        signal, op, threshold = (value.get() for value in controls)
        return {'signal': signal, 'op': op, 'threshold': threshold.strip().replace(',', '.')}

    def _read_rule(self):
        rule = {'name': self.name.get().strip(), 'enabled': self.rule_on.get(),
                'once': self.once.get(), 'a': self._make_condition(self.a),
                'b': self._make_condition(self.b) if self.second_on.get() else None,
                'combine': self.combine.get(), 'beep': self.beep.get(),
                'output': self.output.get(), 'change_v': self.change_v.get(),
                'change_i': self.change_i.get(),
                'target_v': self.target_v.get().strip().replace(',', '.'),
                'target_i': self.target_i.get().strip().replace(',', '.')}
        try:
            valid_rule(rule)
        except (ValueError, KeyError, TypeError) as exc:
            messagebox.showerror('Invalid rule', str(exc), parent=self)
            return None
        return rule

    def _modified(self):
        try:
            self.engine.save()
        except OSError as exc:
            messagebox.showerror('Cannot save rules', str(exc), parent=self)
        self.engine._reset_runtime()
        self.engine.disarm('Rules changed; automation disarmed')
        self.refresh()

    def add(self):
        rule = self._read_rule()
        if rule is None:
            return
        self.engine.rules.append(rule)
        self._modified()
        self._select_index(len(self.engine.rules)-1, load=True)

    def update(self):
        index = self._selected()
        if index is None:
            messagebox.showinfo('Select a rule', 'Choose a rule to update.', parent=self)
            return
        rule = self._read_rule()
        if rule is None:
            return
        self.engine.rules[index] = rule
        self._modified()
        self._select_index(index, load=True)

    def remove(self):
        index = self._selected()
        if index is not None and messagebox.askyesno('Delete rule',
                f"Delete {self.engine.rules[index]['name']}?", parent=self):
            del self.engine.rules[index]
            self._editor_index = None
            self._modified()
            if self.engine.rules:
                self._select_index(min(index, len(self.engine.rules)-1), load=True)
            else:
                self._load_rule()

    def toggle_enabled(self):
        index = self._selected()
        if index is not None:
            rule = self.engine.rules[index]
            rule['enabled'] = not rule['enabled']
            self._modified()
            self._select_index(index, load=True)

    def render_arm_switch(self):
        """Same anti-aliased pill geometry as the main PSU OUTPUT toggle."""
        widget = self.arm_switch
        widget.delete('all')
        active = self.engine.armed
        color = '#15803d' if active else '#475569'
        key = 'on' if active else 'off'
        if Image is not None:
            if key not in self._arm_images:
                self._arm_images[key] = self.app._make_switch_image(active, color)
            widget.create_image(0, 0, image=self._arm_images[key], anchor='nw')
        else:
            widget.create_oval(3, 3, 33, 33, fill=color, outline=color)
            widget.create_rectangle(18, 3, 70, 33, fill=color, outline=color)
            widget.create_oval(55, 3, 85, 33, fill=color, outline=color)
            knob_left = 56 if active else 6
            widget.create_oval(knob_left, 5, knob_left + 26, 31,
                               fill='#f8fafc', outline='#cbd5e1')
        widget.create_text(24 if active else 64, 18,
                           text='ON' if active else 'OFF', fill='white',
                           font=('Segoe UI', 9, 'bold'))

    def toggle_arm(self, _event=None):
        """No confirmation or modal dialog: clicking instantly arms/disarms."""
        if self.engine.armed:
            self.engine.disarm('Disarmed manually')
        elif not self.app.connected:
            self.engine.logs.appendleft('Cannot arm: PSU is disconnected')
            self.refresh()
        elif not any(rule['enabled'] for rule in self.engine.rules):
            self.engine.logs.appendleft('Cannot arm: enable at least one rule')
            self.refresh()
        else:
            # A true condition can trigger on the very next PSU poll.
            self.engine.arm()

    def close(self):
        self.app.automation_dialog = None
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Bench PSU • SCPI Control')
        self.geometry('800x510')
        self.minsize(720, 480)
        self.configure(bg=BG)

        # Create a JSON config with defaults if one does not exist.
        if not CONFIG_FILE.exists():
            try:
                write_configuration(read_configuration())
            except (OSError, ValueError, TypeError) as exc:
                LOGGER.warning('Cannot initialize configuration: %s', exc)
        self.port, self.baudrate, self.response_timeout, self.v_scale, self.i_scale = load_settings()
        self.commands = queue.Queue()
        self.events = queue.Queue()
        self.stop_worker = threading.Event()
        self.worker = None
        self.connected = False
        self.status = tk.StringVar(value='Disconnected')
        self.mode = tk.StringVar(value='MODE: ?')
        self.connection_info = tk.StringVar()
        self.values = {}
        self.adc_labels = {}
        self.mode_bars = {}
        self.controls = {}
        self.output_actual = None  # None until a valid OUTP? response is received.
        self.history = MeasurementHistory()
        self.automation = AutomationEngine(self)
        self.graphs_dialog = None
        self.automation_dialog = None

        self.make_ui()
        # Accommodate Windows display scaling and font metrics without clipping
        # the connection information at the bottom of the window.
        self.update_idletasks()
        # Freeze the meter area's natural height after the first layout pass.
        # Numeric values can change without resizing the measurement cards.
        self.metrics.configure(height=self.metrics.winfo_reqheight())
        self.metrics.pack_propagate(False)
        required_height = self.winfo_reqheight()
        self.minsize(720, max(480, required_height))
        self.geometry(f'800x{max(510, required_height)}')
        self.start_connection()
        self.after(100, self.drain_events)
        self.protocol('WM_DELETE_WINDOW', self.close)

    @staticmethod
    def label(parent, text='', size=12, color='#cbd5e1', **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color,
                        font=('Segoe UI', size), **kwargs)

    def make_ui(self):
        # Reserve the footer first: otherwise Tk's packer can clip it when the
        # window height is only slightly smaller than the total content.
        self.label(self, textvariable=self.connection_info, size=10,
                   color='#94a3b8').pack(side='bottom', fill='x', pady=(2, 8))

        head = tk.Frame(self, bg=BG)
        head.pack(fill='x', padx=20, pady=(12, 5))
        self.label(head, 'POWER SUPPLY', 21, '#f8fafc').pack(side='left')
        def header_icon(symbol, handler, tooltip):
            # Same width/height for all three controls; one icon only.
            btn = tk.Button(head, text=symbol, command=handler, width=3,
                            bg='#334155', fg='#f8fafc', relief='flat', bd=0,
                            highlightthickness=0, takefocus=0,
                            padx=0, pady=5, font=('Segoe UI Symbol', 14),
                            activebackground='#475569', activeforeground='white')
            btn.pack(side='right', padx=(6, 0))
            IconTooltip(btn, tooltip)
            return btn

        self.settings_button = header_icon('⚙', self.open_settings, 'Connection settings')
        self.automation_button = header_icon('⚡', self.open_automation, 'Automation rules')
        self.graphs_button = header_icon('▥', self.open_graphs, 'Graphs and recording')
        self.label(head, color='#93c5fd', size=10,
                   textvariable=self.status).pack(side='right', padx=(0, 4))

        metrics = tk.Frame(self, bg=BG)
        self.metrics = metrics
        metrics.pack(fill='x', padx=15, pady=6)
        # Three uniform grid columns prevent the cards from changing width
        # when ADC or other readings change their character count.
        for col in range(3):
            metrics.grid_columnconfigure(col, weight=1, uniform='meter')
        metrics.grid_rowconfigure(0, weight=1)
        for col, (key, title, unit) in enumerate((
            ('v', 'VOLTAGE', 'V'), ('i', 'CURRENT', 'A'), ('p', 'POWER', 'W')
        )):
            frame = tk.Frame(metrics, bg=PANEL, padx=12, pady=9)
            frame.grid(row=0, column=col, sticky='nsew', padx=5)
            if key in ('v', 'i'):
                # Fixed color associations: green = voltage regulation (CV),
                # red = current regulation (CC). Only the active mode lights up.
                bar = tk.Frame(frame, bg='#334155', height=6)
                bar.pack(side='bottom', fill='x', pady=(9, 0))
                bar.pack_propagate(False)
                self.mode_bars[key] = bar
            if key == 'p':
                # *RST affects the whole instrument, not just its energy meter.
                # Keep the button on the energy line without adding height.
                energy_header = tk.Frame(frame, bg=PANEL)
                energy_header.pack(fill='x')
                self.label(energy_header, 'ENERGY', 10, '#94a3b8').pack(side='left')
                self.reset_button = tk.Button(
                    energy_header, text='Reset PSU', command=self.reset_psu,
                    state='disabled', bg='#334155', fg='#e2e8f0',
                    disabledforeground='#64748b', activebackground='#475569',
                    activeforeground='#f8fafc', relief='flat', bd=0,
                    highlightthickness=0, takefocus=0,
                    font=('Segoe UI', 9), padx=7, pady=1)
                self.reset_button.pack(side='right')
                self.energy_label = self.label(frame, '— Wh', 17, '#7dd3fc')
                self.energy_label.pack(anchor='w', pady=(0, 4))
            heading = tk.Frame(frame, bg=PANEL)
            heading.pack(fill='x')
            self.label(heading, title, 10, '#94a3b8').pack(side='left')
            if key in ('v', 'i'):
                adc = self.label(heading, 'ADC: —', 9, '#94a3b8')
                adc.pack(side='right')
                self.adc_labels[key] = adc
            value = self.label(frame, f'— {unit}', 25, '#7dd3fc')
            value.pack(anchor='w')
            self.values[key] = (value, unit)

        controls = tk.Frame(self, bg=PANEL, padx=15, pady=9)
        controls.pack(fill='x', padx=20, pady=6)
        self.label(controls, 'SETPOINT CONTROLS', 13, '#f8fafc').pack(anchor='w')
        for key, title, maximum, resolution, command, unit in (
            ('set_v', 'Voltage', self.v_scale, 0.01, 'SOUR:VOLT', 'V'),
            ('set_i', 'Current', self.i_scale, 0.001, 'SOUR:CURR', 'A'),
        ):
            self.make_control(controls, key, title, maximum, resolution, command, unit)

        bottom = tk.Frame(self, bg=BG)
        bottom.pack(fill='x', padx=20, pady=(8, 5))
        self.mode_led = tk.Canvas(bottom, width=20, height=20, bg=BG,
                                  highlightthickness=0)
        self.mode_led.pack(side='left', padx=(8, 4))
        self.mode_led_circle = self.mode_led.create_oval(
            3, 3, 17, 17, fill='#475569', outline='#64748b')
        self.label(bottom, textvariable=self.mode, size=13,
                   color='#e2e8f0').pack(side='left', padx=(0, 8))
        # OUTPUT is a single two-position switch. Its state is driven by
        # OUTP? replies, so changes made on the PSU itself are also reflected.
        self.output_switch = tk.Canvas(bottom, width=88, height=36, bg=BG,
                                       highlightthickness=0, bd=0,
                                       relief='flat', takefocus=0,
                                       cursor='arrow')
        # Keep PhotoImage references alive, and reuse each generated bitmap.
        self._switch_images = {}
        self.output_switch.pack(side='right', padx=(4, 8))
        self.output_switch.bind('<Button-1>', self.toggle_output)
        self.label(bottom, 'OUTPUT', size=13,
                   color='#e2e8f0').pack(side='right', padx=(8, 4))
        self.render_output_switch()

        self.refresh_connection_info()

    @staticmethod
    def _make_switch_image(enabled, track_color):
        """Draw a simple, centered switch with anti-aliased edges."""
        scale = 4
        width, height = 88, 36
        image = Image.new('RGB', (width * scale, height * scale), BG)
        draw = ImageDraw.Draw(image)

        def rect(coords):
            return tuple(round(c * scale) for c in coords)

        # One clean pill (no shadow or accent arc above the track).
        draw.rounded_rectangle(rect((3, 3, 85, 33)), radius=15 * scale,
                               fill=track_color, outline='#64748b' if not enabled
                               else '#16a34a', width=scale)

        # Both the knob and the track are centered at y=18. The knob has
        # symmetrical clearance above and below the track (2 px each).
        knob_left = 56 if enabled else 6
        draw.ellipse(rect((knob_left, 5, knob_left + 26, 31)),
                     fill='#f8fafc', outline='#cbd5e1', width=scale)

        return ImageTk.PhotoImage(
            image.resize((width, height), Image.Resampling.LANCZOS)
        )

    def render_output_switch(self):
        """Display the current local state (refreshed by each OUTP? reply)."""
        widget = self.output_switch
        widget.delete('all')
        if self.connected and self.output_actual is not None:
            visual_on = self.output_actual
            color = '#15803d' if visual_on else '#475569'
            caption = 'ON' if visual_on else 'OFF'
            key = 'on' if visual_on else 'off'
        else:
            visual_on = False
            color, caption = '#334155', '?'
            key = 'unknown'

        if Image is not None:
            if key not in self._switch_images:
                self._switch_images[key] = self._make_switch_image(visual_on, color)
            widget.create_image(0, 0, image=self._switch_images[key], anchor='nw')
        else:
            # Native Canvas fallback with the same centered geometry.
            widget.create_oval(3, 3, 33, 33, fill=color, outline=color)
            widget.create_rectangle(18, 3, 70, 33, fill=color, outline=color)
            widget.create_oval(55, 3, 85, 33, fill=color, outline=color)
            knob_left = 56 if visual_on else 6
            widget.create_oval(knob_left, 5, knob_left + 26, 31,
                               fill='#f8fafc', outline='#cbd5e1')

        widget.create_text(24 if visual_on else 64, 18, text=caption,
                           fill='#ffffff', font=('Segoe UI', 9, 'bold'))
        widget.configure(cursor='hand2' if self.connected and
                         self.output_actual is not None else 'arrow')

    def toggle_output(self, _event=None):
        # Flip immediately; let the next normal OUTP? update reconcile with
        # the physical PSU state if the command was ignored or failed.
        if not self.connected or self.output_actual is None:
            return
        self.output_actual = not self.output_actual
        self.render_output_switch()
        self.commands.put(f'OUTP {int(self.output_actual)}')

    def update_output_state(self, raw_value):
        # The PSU is authoritative. No pending state or extra confirmation timer.
        normalized = str(raw_value).strip()
        self.output_actual = normalized == '1' if normalized in ('0', '1') else None
        self.render_output_switch()

    def reset_output_switch(self):
        self.output_actual = None
        self.render_output_switch()

    def make_control(self, parent, key, title, maximum, resolution, command, unit):
        line = tk.Frame(parent, bg=PANEL)
        line.pack(fill='x', pady=5)
        self.label(line, title, 12, '#e2e8f0', width=8,
                   anchor='w').pack(side='left', padx=(0, 4))
        variable = tk.DoubleVar(value=0)
        entry = tk.Entry(line, width=9, bg='#334155', fg='white',
                         insertbackground='white', relief='flat',
                         font=('Segoe UI', 12), justify='center')
        state = {'var': variable, 'entry': entry, 'editing': False,
                 'syncing': False, 'slider_active': False,
                 'pending': None, 'pending_until': 0.0}
        self.controls[key] = state

        def slider_changed(_value):
            if state['syncing'] or not state['slider_active']:
                return
            state['editing'] = True
            entry.delete(0, 'end')
            entry.insert(0, f'{variable.get():.3f}')

        slider = tk.Scale(line, from_=0, to=maximum, resolution=resolution,
                          orient='horizontal', variable=variable, length=300,
                          bg=PANEL, fg='#e2e8f0', troughcolor='#334155',
                          highlightthickness=0, showvalue=False,
                          command=slider_changed)
        state['slider'] = slider
        slider.pack(side='left', fill='x', expand=True)
        slider.bind('<ButtonPress-1>', lambda _event: state.update(slider_active=True, editing=True))
        slider.bind('<ButtonRelease-1>', lambda _event: state.update(slider_active=False))
        slider.bind('<KeyPress>', lambda _event: state.update(slider_active=True, editing=True))
        slider.bind('<KeyRelease>', lambda _event: state.update(slider_active=False))
        entry.pack(side='left', padx=10)
        entry.insert(0, '0.000')

        def apply():
            try:
                value = float(entry.get().replace(',', '.'))
                if not math.isfinite(value):
                    raise ValueError
            except ValueError:
                messagebox.showerror('Invalid value', 'Enter a finite numeric value.')
                return
            if not self.connected:
                messagebox.showwarning('Disconnected', 'No serial connection.')
                return
            state['pending'] = value
            state['pending_until'] = time.monotonic() + 3
            state['editing'] = False
            self.sync_control(state, value)
            self.commands.put(f'{command} {value:.3f}')
            self.focus_set()

        tk.Button(line, text='Apply', command=apply, bg='#2563eb',
                  fg='white', relief='flat', padx=14, pady=5).pack(side='left')
        entry.bind('<Return>', lambda _event: apply())
        entry.bind('<KeyPress>', lambda _event: state.update(editing=True))

        actual = self.label(parent, f'Device setpoint: — {unit}', 11, '#86efac')
        actual.pack(anchor='w', padx=86, pady=(0, 2))
        state['actual'] = actual
        state['unit'] = unit
        state['resolution'] = resolution

    @staticmethod
    def expand_slider_if_needed(state, value):
        """Allow larger (or negative) setpoints without editing the program."""
        slider = state['slider']
        lo = float(slider.cget('from'))
        hi = float(slider.cget('to'))
        if value < lo:
            slider.configure(from_=min(value * 1.2, value - 0.01))
        if value > hi:
            slider.configure(to=max(value * 1.2, hi * 1.5))

    @classmethod
    def sync_control(cls, state, value):
        state['syncing'] = True
        try:
            cls.expand_slider_if_needed(state, value)
            state['var'].set(value)
            entry = state['entry']
            entry.delete(0, 'end')
            entry.insert(0, f'{value:.3f}')
        finally:
            state['syncing'] = False

    def update_setpoint(self, key, raw_value, dac_raw):
        state = self.controls[key]
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            state['actual'].config(text=f'Device setpoint: {raw_value} {state["unit"]} (DAC: {dac_raw})')
            return
        state['actual'].config(text=f'Device setpoint: {value:.3f} {state["unit"]} (DAC: {dac_raw})')
        self.expand_slider_if_needed(state, value)
        if state['pending'] is not None:
            if abs(value - state['pending']) <= state['resolution'] / 2 + 0.00001:
                state['pending'] = None
            elif time.monotonic() < state['pending_until']:
                return
            else:
                state['pending'] = None

        if state['editing']:
            return
        # The focused widget may be an internal ttk.Combobox popdown that Tk
        # created itself. tkinter.focus_get() tries to convert its Tcl path
        # into a registered Python widget and can raise KeyError('popdown').
        # Compare the raw Tcl focus path instead; it never resolves widgets.
        try:
            entry_has_focus = str(self.tk.call('focus')) == str(state['entry'])
        except tk.TclError:
            entry_has_focus = False
        if entry_has_focus:
            return
        self.sync_control(state, value)

    def open_graphs(self):
        if self.graphs_dialog and self.graphs_dialog.winfo_exists():
            self.graphs_dialog.lift()
            self.graphs_dialog.focus_set()
            return
        self.graphs_dialog = GraphsDialog(self)

    def open_automation(self):
        if self.automation_dialog and self.automation_dialog.winfo_exists():
            self.automation_dialog.lift()
            self.automation_dialog.focus_set()
            return
        self.automation_dialog = AutomationDialog(self)

    def refresh_connection_info(self):
        self.connection_info.set(f'{self.port} • {self.baudrate} baud • SCPI')

    def start_connection(self):
        self.automation.disarm('Connection changed; automation disarmed')
        self.connected = False
        self.reset_button.configure(state='disabled')
        self.reset_output_switch()
        self.status.set(f'Connecting to {self.port}…')
        self.commands = queue.Queue()
        self.events = queue.Queue()
        self.stop_worker = threading.Event()
        self.worker = SerialWorker(self.port, self.baudrate, self.response_timeout,
                                   self.commands, self.events, self.stop_worker)
        self.worker.start()
        self.refresh_connection_info()

    def reconnect(self):
        self.automation.disarm('Reconnecting; automation disarmed')
        self.connected = False
        self.reset_button.configure(state='disabled')
        self.reset_output_switch()
        self.status.set('Reconnecting…')
        self.stop_worker.set()
        # Do not open the new port until the old Serial handle has closed.
        self.wait_for_worker()

    def wait_for_worker(self):
        if self.worker is not None and self.worker.is_alive():
            self.after(100, self.wait_for_worker)
            return
        self.reset_readings()
        self.start_connection()

    def reset_readings(self):
        self.update_mode_indicator('?', '?')
        self.reset_output_switch()
        self.energy_label.config(text='— Wh')
        for widget, unit in self.values.values():
            widget.config(text=f'— {unit}')
        for adc in self.adc_labels.values():
            adc.config(text='ADC: —')
        for state in self.controls.values():
            state['pending'] = None
            state['editing'] = False
            state['actual'].config(text=f'Device setpoint: — {state["unit"]} (DAC: —)')

    def open_settings(self):
        if getattr(self, '_settings_dialog', None) is not None:
            self._settings_dialog.lift()
            return

        dialog = tk.Toplevel(self)
        self._settings_dialog = dialog
        dialog.title('Connection settings')
        dialog.configure(bg=PANEL)
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        content = tk.Frame(dialog, bg=PANEL, padx=20, pady=18)
        content.pack(fill='both', expand=True)
        port_var = tk.StringVar(value=self.port)
        baud_var = tk.StringVar(value=str(self.baudrate))
        timeout_var = tk.StringVar(value=str(self.response_timeout))
        voltage_scale_var = tk.StringVar(value=str(self.v_scale))
        current_scale_var = tk.StringVar(value=str(self.i_scale))

        self.label(content, 'COM port', 11, '#f8fafc').grid(
            row=0, column=0, sticky='w', pady=(0, 10))
        port_picker = ttk.Combobox(content, textvariable=port_var,
                                    width=24, state='normal')
        port_picker.grid(row=0, column=1, sticky='ew', padx=(12, 5), pady=(0, 10))

        def refresh_ports():
            devices = sorted({port.device for port in list_ports.comports()})
            if port_var.get().strip() not in devices:
                devices.append(port_var.get().strip())
            port_picker['values'] = sorted(filter(None, devices))

        tk.Button(content, text='Refresh', command=refresh_ports,
                  bg='#334155', fg='white', relief='flat', padx=8).grid(
                      row=0, column=2, pady=(0, 10))
        self.label(content, 'Baudrate', 11, '#f8fafc').grid(
            row=1, column=0, sticky='w', pady=(0, 14))
        baud_picker = ttk.Combobox(content, textvariable=baud_var, width=24,
                                     values=('9600', '19200', '38400', '57600', '115200'),
                                     state='normal')
        baud_picker.grid(row=1, column=1, sticky='ew', padx=(12, 5), pady=(0, 14))
        refresh_ports()

        for row, title, var in (
            (2, 'Response timeout (s)', timeout_var),
            (3, 'Voltage slider range (V)', voltage_scale_var),
            (4, 'Current slider range (A)', current_scale_var),
        ):
            self.label(content, title, 11, '#f8fafc').grid(
                row=row, column=0, sticky='w', pady=(0, 12))
            tk.Entry(content, textvariable=var, width=26,
                     bg='#334155', fg='white', insertbackground='white',
                     relief='flat', font=('Segoe UI', 11)).grid(
                row=row, column=1, sticky='ew', padx=(12, 5), pady=(0, 12))

        buttons = tk.Frame(content, bg=PANEL)
        buttons.grid(row=5, column=0, columnspan=3, sticky='e')

        def close_dialog():
            self._settings_dialog = None
            dialog.destroy()

        def save():
            port = port_var.get().strip()
            try:
                baudrate = int(baud_var.get().strip())
                timeout = float(timeout_var.get().strip().replace(',', '.'))
                voltage_scale = float(voltage_scale_var.get().strip().replace(',', '.'))
                current_scale = float(current_scale_var.get().strip().replace(',', '.'))
            except ValueError:
                baudrate, timeout, voltage_scale, current_scale = 0, 0, 0, 0
            if (not port or baudrate <= 0 or
                not all(math.isfinite(x) and x > 0
                        for x in (timeout, voltage_scale, current_scale))):
                messagebox.showerror('Invalid settings',
                                     'Enter a COM port, positive baudrate, '
                                     'timeout and slider ranges.', parent=dialog)
                return
            try:
                save_settings(port, baudrate, timeout, voltage_scale, current_scale)
            except OSError as error:
                messagebox.showerror('Cannot save settings',
                                     f'Could not write {CONFIG_FILE}:\n{error}',
                                     parent=dialog)
                return
            serial_changed = (port, baudrate, timeout) != (
                self.port, self.baudrate, self.response_timeout)
            self.port, self.baudrate, self.response_timeout = port, baudrate, timeout
            self.v_scale, self.i_scale = voltage_scale, current_scale
            for key, rng in (('set_v', voltage_scale), ('set_i', current_scale)):
                state = self.controls[key]
                # Settings change the preferred slider size; currently shown
                # values may expand it to remain usable, never clamp readings.
                state['slider'].configure(from_=0, to=rng)
                try:
                    shown = float(state['entry'].get().replace(',', '.'))
                    if math.isfinite(shown):
                        self.expand_slider_if_needed(state, shown)
                except ValueError:
                    pass
            self.refresh_connection_info()
            close_dialog()
            if serial_changed or not self.connected:
                self.reconnect()

        tk.Button(buttons, text='Cancel', command=close_dialog,
                  bg='#475569', fg='white', relief='flat', padx=14,
                  pady=6).pack(side='right', padx=(8, 0))
        tk.Button(buttons, text='Save & connect', command=save,
                  bg='#2563eb', fg='white', relief='flat', padx=14,
                  pady=6).pack(side='right')
        dialog.protocol('WM_DELETE_WINDOW', close_dialog)
        dialog.bind('<Escape>', lambda _event: close_dialog())
        port_picker.focus_set()

    def reset_psu(self):
        # *RST is a full instrument reset; it must not be presented as a
        # harmless energy-counter-only reset.
        if not self.connected:
            messagebox.showwarning('Disconnected', 'No serial connection.', parent=self)
            return
        if not messagebox.askyesno(
            'Reset power supply',
            'Send *RST to the power supply?\n\n'
            'This can reset the energy counter, output state, and voltage/current '
            'setpoints depending on the PSU firmware.',
            icon='warning', default='no', parent=self
        ):
            return
        # Disarm automatic actions: the PSU can change setpoints and output during *RST.
        self.automation.disarm('PSU reset; automation disarmed')
        # Do not clear readings, sliders, edit fields or their focus here.
        # Cancel only an outstanding Apply grace period: otherwise it can
        # briefly prevent the regular poll from syncing post-reset setpoints.
        for control in self.controls.values():
            control['pending'] = None
        # The worker sends the command in sequence with other SCPI traffic.
        # The next normal reading round is the sole source of GUI values.
        self.commands.put('*RST')

    def update_mode_indicator(self, mode, output):
        normalized = str(mode).strip().upper()
        enabled = str(output).strip() == '1'
        cv_active = enabled and normalized == 'CV'
        cc_active = enabled and normalized == 'CC'

        # Highlight only the card associated with the active regulation mode.
        self.mode_bars['v'].config(bg='#22c55e' if cv_active else '#334155')
        self.mode_bars['i'].config(bg='#ef4444' if cc_active else '#334155')

        if cv_active:
            color, border = '#22c55e', '#86efac'
        elif cc_active:
            color, border = '#ef4444', '#fca5a5'
        else:
            color, border = '#475569', '#64748b'
        self.mode_led.itemconfig(self.mode_led_circle, fill=color, outline=border)
        if str(output).strip() not in ('0', '1'):
            self.mode.set('MODE: ?')
        else:
            self.mode.set(f'MODE: {normalized}' if enabled else 'MODE: OFF')

    def drain_events(self):
        # Schedule BEFORE processing: even an unforeseen error in a single
        # reading must not permanently stop the main display after this tick.
        self.after(100, self.drain_events)
        try:
            # Bounded batch: a backlog of UART events must not monopolize Tk.
            for _ in range(200):
                try:
                    kind, data = self.events.get_nowait()
                except queue.Empty:
                    break
                if kind == 'connected':
                    self.connected = True
                    self.reset_button.configure(state='normal')
                    self._device_id = data
                    self.status.set(f'Connected: {data}')
                    self.render_output_switch()
                elif kind == 'readings':
                    # A complete, validated response round restored sync.
                    if self.connected and not self.status.get().startswith('Connected:'):
                        self.status.set('Connected: ' + getattr(self, '_device_id', self.port))
                    for key in ('v', 'i', 'p'):
                        widget, unit = self.values[key]
                        try:
                            widget.config(text=f'{float(data[key]):.3f} {unit}')
                        except (TypeError, ValueError):
                            widget.config(text=f'{data[key]} {unit}')
                    self.update_setpoint('set_v', data['set_v'], data['dac_v'])
                    self.update_setpoint('set_i', data['set_i'], data['dac_i'])
                    self.adc_labels['v'].config(text=f'ADC: {data["raw_v"]}')
                    self.adc_labels['i'].config(text=f'ADC: {data["raw_i"]}')
                    self.update_mode_indicator(data['mode'], data['out'])
                    self.update_output_state(data['out'])
                    self.energy_label.config(text=f'{data["e"]} Wh')
                    # Reuse the SAME complete polling result. No extra UART traffic.
                    self.history.add(data)
                    self.automation.observe(data)
                elif kind == 'query_error':
                    # Keep previous complete readings visible during recovery.
                    command = str(data).split(': ', 1)[0]
                    self.status.set(f'SCPI retry ({command})…')
                elif kind == 'error':
                    self.status.set(f'Error: {data}')
                elif kind == 'disconnected':
                    self.automation.disarm('Disconnected; automation disarmed')
                    self.connected = False
                    self.reset_button.configure(state='disabled')
                    self.reset_output_switch()
                    self.update_mode_indicator('?', '?')
                    if not self.stop_worker.is_set():
                        if not self.status.get().startswith('Error:'):
                            self.status.set('Disconnected')
        except Exception as exc:
            LOGGER.exception('Main PSU readings/UI update failed')
            self.status.set(f'GUI error: {type(exc).__name__} (see psu_control_gui.log)')

    def report_callback_exception(self, exc_type, exc_value, exc_tb):
        # Log Tk callbacks too: pythonw.exe has no console for tracebacks.
        LOGGER.error('Uncaught Tk callback exception',
                     exc_info=(exc_type, exc_value, exc_tb))
        try:
            self.status.set('GUI callback error (see psu_control_gui.log)')
        except tk.TclError:
            pass

    def close(self):
        self.stop_worker.set()
        self.history.stop_logging()
        self.destroy()


if __name__ == '__main__':
    App().mainloop()
