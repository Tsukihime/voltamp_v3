"""SCPI laboratory power supply GUI.

Requires: pip install pyserial
Settings are stored in psu_control_gui.ini beside this script.
SOUR:*:RAW? readings are labeled DAC (setpoint raw) as in PSU firmware protocol.
"""

import configparser
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import serial
from serial.tools import list_ports

DEFAULT_PORT = 'COM4'
DEFAULT_BAUDRATE = 9600
CONFIG_FILE = Path(__file__).resolve().with_name('psu_control_gui.ini')
VOLTAGE_MAX = 30.0
CURRENT_MAX = 3.0
POLL_SECONDS = 0.1  # Pause between completed query rounds; UART throughput sets the actual rate.
BG = '#101827'
PANEL = '#1e293b'


def load_settings():
    parser = configparser.ConfigParser()
    try:
        parser.read(CONFIG_FILE, encoding='utf-8')
        port = parser.get('serial', 'port', fallback=DEFAULT_PORT).strip() or DEFAULT_PORT
        baudrate = parser.getint('serial', 'baudrate', fallback=DEFAULT_BAUDRATE)
        if baudrate <= 0:
            raise ValueError('Baudrate must be positive')
        return port, baudrate
    except (OSError, ValueError, configparser.Error):
        return DEFAULT_PORT, DEFAULT_BAUDRATE


def save_settings(port, baudrate):
    parser = configparser.ConfigParser()
    parser['serial'] = {'port': port, 'baudrate': str(baudrate)}
    with CONFIG_FILE.open('w', encoding='utf-8') as output:
        parser.write(output)


class SerialWorker(threading.Thread):
    QUERIES = (
        ('set_v', 'SOUR:VOLT?'),
        ('set_i', 'SOUR:CURR?'),
        ('dac_v', 'SOUR:VOLT:RAW?'),
        ('dac_i', 'SOUR:CURR:RAW?'),
        ('out', 'OUTP?'),
        ('v', 'MEAS:VOLT?'),
        ('i', 'MEAS:CURR?'),
        ('p', 'MEAS:POW?'),
        ('e', 'MEAS:ENER?'),
        ('mode', 'MEAS:MODE?'),
        ('raw_v', 'MEAS:VOLT:RAW?'),
        ('raw_i', 'MEAS:CURR:RAW?'),
    )

    def __init__(self, port, baudrate, commands, events, stop):
        super().__init__(daemon=True)
        self.port = port
        self.baudrate = baudrate
        self.commands = commands
        self.events = events
        self.stop = stop

    @staticmethod
    def query(ser, command):
        ser.write((command + '\n').encode('ascii'))
        response = ser.readline().decode('ascii', errors='replace').strip()
        if not response or response.startswith('ERR:'):
            raise ValueError(f'{command}: {response or "no response"}')
        return response

    def run(self):
        try:
            with serial.Serial(self.port, self.baudrate, timeout=0.4, write_timeout=0.5) as ser:
                if self.stop.wait(2):
                    return
                self.events.put(('connected', self.query(ser, '*IDN?')))
                next_poll = 0.0
                while not self.stop.is_set():
                    try:
                        while True:
                            command = self.commands.get_nowait()
                            ser.write((command + '\n').encode('ascii'))
                    except queue.Empty:
                        pass

                    if time.monotonic() >= next_poll:
                        readings = {}
                        for key, command in self.QUERIES:
                            if self.stop.is_set():
                                break
                            try:
                                readings[key] = self.query(ser, command)
                            except ValueError:
                                # Unsupported query: show a dash, do not stop polling.
                                readings[key] = '—'
                        if not self.stop.is_set():
                            self.events.put(('readings', readings))
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

        self.port, self.baudrate = load_settings()
        self.commands = queue.Queue()
        self.events = queue.Queue()
        self.stop_worker = threading.Event()
        self.worker = None
        self.connected = False
        self.status = tk.StringVar(value='Disconnected')
        self.output = tk.StringVar(value='OUTPUT: ?')
        self.mode = tk.StringVar(value='MODE: ?')
        self.connection_info = tk.StringVar()
        self.values = {}
        self.adc_labels = {}
        self.mode_bars = {}
        self.controls = {}

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
                self.label(frame, 'ENERGY', 10, '#94a3b8').pack(anchor='w')
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
            ('set_v', 'Voltage', VOLTAGE_MAX, 0.01, 'SOUR:VOLT', 'V'),
            ('set_i', 'Current', CURRENT_MAX, 0.001, 'SOUR:CURR', 'A'),
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
        self.label(bottom, textvariable=self.output, size=13,
                   color='#e2e8f0').pack(side='left', padx=20)
        tk.Button(bottom, text='OUTPUT ON', command=lambda: self.send('OUTP 1'),
                  bg='#15803d', fg='white', relief='flat', padx=16,
                  pady=7).pack(side='right', padx=4)
        tk.Button(bottom, text='OUTPUT OFF', command=lambda: self.send('OUTP 0'),
                  bg='#b91c1c', fg='white', relief='flat', padx=16,
                  pady=7).pack(side='right', padx=4)

        self.refresh_connection_info()

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
                if not 0 <= value <= maximum:
                    raise ValueError
            except ValueError:
                messagebox.showerror('Invalid value', f'Enter a value from 0 to {maximum}.')
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
        state['dac_raw'] = '—'
        state['unit'] = unit
        state['resolution'] = resolution

    @staticmethod
    def sync_control(state, value):
        state['syncing'] = True
        try:
            state['var'].set(value)
            entry = state['entry']
            entry.delete(0, 'end')
            entry.insert(0, f'{value:.3f}')
        finally:
            state['syncing'] = False

    def update_setpoint(self, key, raw_value, dac_raw):
        state = self.controls[key]
        state['dac_raw'] = dac_raw
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            state['actual'].config(text=f'Device setpoint: {raw_value} {state["unit"]} (DAC: {dac_raw})')
            return
        state['actual'].config(text=f'Device setpoint: {value:.3f} {state["unit"]} (DAC: {dac_raw})')
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
        self.status.set(f'Connecting to {self.port}…')
        self.commands = queue.Queue()
        self.events = queue.Queue()
        self.stop_worker = threading.Event()
        self.worker = SerialWorker(self.port, self.baudrate,
                                   self.commands, self.events, self.stop_worker)
        self.worker.start()
        self.refresh_connection_info()

    def reconnect(self):
        self.connected = False
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
        self.update_mode_indicator('?', '0')
        self.mode.set('MODE: ?')
        self.output.set('OUTPUT: ?')
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

        buttons = tk.Frame(content, bg=PANEL)
        buttons.grid(row=2, column=0, columnspan=3, sticky='e')

        def close_dialog():
            self._settings_dialog = None
            dialog.destroy()

        def save():
            port = port_var.get().strip()
            try:
                baudrate = int(baud_var.get().strip())
            except ValueError:
                baudrate = 0
            if not port or baudrate <= 0:
                messagebox.showerror('Invalid settings',
                                     'Enter a COM port and a positive baudrate.',
                                     parent=dialog)
                return
            try:
                save_settings(port, baudrate)
            except OSError as error:
                messagebox.showerror('Cannot save settings',
                                     f'Could not write {CONFIG_FILE}:\n{error}',
                                     parent=dialog)
                return
            changed = (port, baudrate) != (self.port, self.baudrate)
            self.port, self.baudrate = port, baudrate
            self.refresh_connection_info()
            close_dialog()
            if changed or not self.connected:
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

    def send(self, command):
        if not self.connected:
            messagebox.showwarning('Disconnected', 'No serial connection.')
            return
        self.commands.put(command)

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
        self.mode.set(f'MODE: {mode}' if enabled else 'MODE: OFF')

    def drain_events(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == 'connected':
                    self.connected = True
                    self.status.set(f'Connected: {data}')
                elif kind == 'readings':
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
                    self.output.set('OUTPUT: ON' if data['out'] == '1'
                                    else 'OUTPUT: OFF' if data['out'] == '0'
                                    else f'OUTPUT: {data["out"]}')
                    self.energy_label.config(text=f'{data["e"]} Wh')
                elif kind == 'error':
                    self.status.set(f'Error: {data}')
                elif kind == 'disconnected':
                    self.connected = False
                    self.update_mode_indicator('?', '0')
                    self.mode.set('MODE: ?')
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
