"""SCPI laboratory power supply GUI.

Requires: pip install pyserial
SCPI replies are type-checked. One request is read at a time, with a configurable timeout.
Settings are stored in psu_control_gui.ini beside this script.
SOUR:*:RAW? readings are labeled DAC (setpoint raw) as in PSU firmware protocol.
"""

import configparser
import math
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
CONFIG_FILE = Path(__file__).resolve().with_name('psu_control_gui.ini')
DEFAULT_VOLTAGE_SCALE = 30.0   # Initial slider range, not a limit on commands
DEFAULT_CURRENT_SCALE = 3.0   # Sliders grow if a setpoint exceeds their range
DEFAULT_RESPONSE_TIMEOUT = 2.0
POLL_SECONDS = 0.1  # Pause between completed query rounds; UART throughput sets the actual rate.
BG = '#101827'
PANEL = '#1e293b'


def load_settings():
    parser = configparser.ConfigParser()
    try:
        parser.read(CONFIG_FILE, encoding='utf-8')
        port = parser.get('serial', 'port', fallback=DEFAULT_PORT).strip() or DEFAULT_PORT
        baudrate = parser.getint('serial', 'baudrate', fallback=DEFAULT_BAUDRATE)
        timeout = parser.getfloat('serial', 'timeout', fallback=DEFAULT_RESPONSE_TIMEOUT)
        voltage_scale = parser.getfloat('controls', 'voltage_scale', fallback=DEFAULT_VOLTAGE_SCALE)
        current_scale = parser.getfloat('controls', 'current_scale', fallback=DEFAULT_CURRENT_SCALE)
        if (baudrate <= 0 or not all(math.isfinite(v) and v > 0
                                    for v in (timeout, voltage_scale, current_scale))):
            raise ValueError('Invalid serial or slider settings')
        return port, baudrate, timeout, voltage_scale, current_scale
    except (OSError, ValueError, configparser.Error):
        return (DEFAULT_PORT, DEFAULT_BAUDRATE, DEFAULT_RESPONSE_TIMEOUT,
                DEFAULT_VOLTAGE_SCALE, DEFAULT_CURRENT_SCALE)


def save_settings(port, baudrate, timeout, voltage_scale, current_scale):
    parser = configparser.ConfigParser()
    parser.read(CONFIG_FILE, encoding='utf-8')
    parser['serial'] = {'port': port, 'baudrate': str(baudrate),
                        'timeout': str(timeout)}
    parser['controls'] = {'voltage_scale': str(voltage_scale),
                          'current_scale': str(current_scale)}
    with CONFIG_FILE.open('w', encoding='utf-8') as output:
        parser.write(output)


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


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Bench PSU • SCPI Control')
        self.geometry('800x510')
        self.minsize(720, 480)
        self.configure(bg=BG)

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
        tk.Button(head, text='⚙', command=self.open_settings,
                  bg='#334155', fg='#f8fafc', relief='flat', padx=10,
                  pady=6, font=('Segoe UI Symbol', 14)).pack(side='right', padx=(12, 0))
        self.label(head, color='#93c5fd', size=10,
                   textvariable=self.status).pack(side='right')

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

        if state['editing'] or self.focus_get() == state['entry']:
            return
        self.sync_control(state, value)

    def refresh_connection_info(self):
        self.connection_info.set(f'{self.port} • {self.baudrate} baud • SCPI')

    def start_connection(self):
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
        try:
            while True:
                kind, data = self.events.get_nowait()
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
                elif kind == 'query_error':
                    # Keep previous complete readings visible during recovery.
                    command = str(data).split(': ', 1)[0]
                    self.status.set(f'SCPI retry ({command})…')
                elif kind == 'error':
                    self.status.set(f'Error: {data}')
                elif kind == 'disconnected':
                    self.connected = False
                    self.reset_button.configure(state='disabled')
                    self.reset_output_switch()
                    self.update_mode_indicator('?', '?')
                    if not self.stop_worker.is_set():
                        if not self.status.get().startswith('Error:'):
                            self.status.set('Disconnected')
        except queue.Empty:
            pass
        self.after(100, self.drain_events)

    def close(self):
        self.stop_worker.set()
        self.destroy()


if __name__ == '__main__':
    App().mainloop()
