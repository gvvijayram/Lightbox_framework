#!/usr/bin/env python3
import os
import sys
try:
    import serial
except Exception:
    raise Exception('Failed to import "serial" module\nTry to install "pyserial": \033[91mpython3 -m pip install pyserial --user\033[0m')
import time
import numpy as np
from scipy.interpolate import interp1d
import chromameters as CMM

_CONFIG_ARRI = {'baudrate': 57600}

_DEVICE_CONFIG = {'dxo': {},
                  'arri': _CONFIG_ARRI,
                  'solbox': {},
                  'dummy': None}

WAITING_KEY_WORD = {'dxo': 'SerialToDmx',
                    'solbox': 'SolBox'}


class DummySerial:
    def __init__(self, port='dummy', baudrate=57600, **kwargs):
        self.port = port
        self.baudrate = baudrate
        self._open = False

    def open(self):
        self._open = True

    def close(self):
        self._open = False

    def write(self, data):
        pass

    def read(self, size=0):
        return b''

    def isOpen(self):
        return self._open

    def inWaiting(self):
        return 0

    @property
    def in_waiting(self):
        return self.inWaiting()

def port_selector(ports, selection=None):
    def select_list_ports(ports):
        for enum,p in enumerate(ports):
            print('{}: {}'.format(enum, p))
        index = input('Select serial port: ')
        return port_selector(ports, selection=index)

    if len(ports) == 0:
        raise Exception('No valid port available, try reset cable or power toggle light box')
    if len(ports) == 1:
        return ports[0]
    if selection is not None:
        try:
            index = int(selection)
            return ports[index]
        except:
            pass
        possible_ports = [port for port in ports if selection in port]
        if len(possible_ports) < len(ports):
            return port_selector(possible_ports, selection)
        return select_list_ports(ports)

    else: # Selection is None
        return select_list_ports(ports)


class light_source(object):
    def __init__(self, port=None, light_source=None, calibration_mode=True, verbose=1, dummy=False):
        self._chromameters = {} # Class reference
        self.chromameters = {} # Connected object reference
        self.verbose = verbose
        self.calibration_mode = calibration_mode
        ports = self.connected_devices()
        self.chromameter_connected(ports)
        # Remove the ports used by chromameters.
        for port_name in self._chromameters:
            ports.remove(port_name)

        if dummy or light_source == 'dummy':
            self.port = 'dummy'
        else:
            if len(ports) == 0:
                raise Exception('No connected serial device for light source')
            self.port = port_selector(ports, selection=port)
        self.serial = None
        self.luminance = 0.0
        self.cct = 5000
        self.timeout = 1
        self.abs_luminance = None
        self.flicker_freq = 0
        self._mapping = {'arri': self._set_light_arri,
                         'solbox': self._set_light_iq_sol,
                         'dxo': self._set_light_dxo,
                         'dummy': lambda luminance=None, cct=None, **kwargs : None}
        self.selected_source = light_source if light_source is not None else None
        if light_source == 'dummy':
            return None
        self._initial_connect(self.port)

    def chromameter_connected(self, ports):
        for port in ports:
            for ident in CMM.CHROMA_METERS_IDENTIFIER:
                if ident in port:
                    self._chromameters[port] = CMM.CHROMA_METERS[CMM.CHROMA_METERS_IDENTIFIER[ident]]
                    break

    def _initial_connect(self, port):
        if self.selected_source is None:
            self.selected_source = self.identify_device(port)
        dev_config = _DEVICE_CONFIG[self.selected_source]
        if self.verbose > 1:
            print(f'Connecting to serial: {port}')
        if self.port == 'dummy':
            self.serial = DummySerial()
        else:
            self.serial = serial.Serial(port, **dev_config)

        if self.verbose > 1:
            print(f'Connection status: {self.serial}')

        for name, Chromameter in self._chromameters.items():
            self.chromameters[name] = Chromameter(name)
            if self.verbose > 1:
                print('Chroma meter connected: {}'.format(self.chromameters[name]))
            if self.calibration_mode:
                self.chromameters[name].start()

    def connected_devices(self):
        ports = []
        if sys.platform == 'darwin':
            # OSX system
            ports = [os.path.join('/dev', d) for d in os.listdir('/dev') if 'cu.usb' in d.lower()]

        return ports

    def _open(self):
        if self.serial is not None and self.serial.isOpen():
            self.reconnect()
        else:
            self._initial_connect(self.port)
        return self.serial

    def disconnect(self):
        if self.device == 'dxo':
            self.write('16c0w'.encode())
        if self.device == 'iq_sol_lightbox':
            self.write('L 2700 T 0'.encode())
        self.close()

    def check_still_connected(self):
        return self.port in self.connected_devices()

    def reconnect(self):
        if self.check_still_connected():
            self.serial.close()
            time.sleep(0.1)
            self.serial.open()
        else:
            self.serial.close()
            raise Exception('Device no longer connected')

    def identify_device(self, port):
        ser_obj = serial.Serial(port)
        self.serial = ser_obj
        ser_obj.write(bytearray([0]))
        time.sleep(1)
        bytes_in_waiting = ser_obj.inWaiting()
        device = None
        if bytes_in_waiting:
            data = ser_obj.read(bytes_in_waiting).decode()
            for kw in WAITING_KEY_WORD:
                if WAITING_KEY_WORD[kw] in data:
                    self.selected_source = kw
                    break
        self.serial.close()
        # Hardcoded since Arri light doesn't give a reply when connecting.
        if self.selected_source is None:
            self.selected_source = 'arri'
        if self.verbose > 1:
            print('Device connected: <{}> at port: <{}>'.format(self.selected_source, self.port))
        return self.selected_source

    def get_avg_luminance(self):
        return np.mean([cm.get_luminance for cm in self.chromameters.values()])

    def set_light_abs(self, abs_luminance, cct=None, tolerance=0.01, **kwargs):
        """
        Set light condition with absolute luminance measured from chroma meter.
        """
        if len(self.chromameters) == 0 or self.calibration_mode == False:
            raise Exception('No connected chroma meters')
        self.abs_luminance = abs_luminance
        chroma_lux = self.get_avg_luminance()
        ratio = self.abs_luminance / chroma_lux
        prev_lum = None
        max_iterations = 10
        while np.abs(ratio - 1.0) > tolerance and max_iterations or cct != self.cct:
            if prev_lum is None:
                self.set_light(luminance=0.1, cct=cct)
            elif self.luminance < 1.0/(65535):
                self.set_light(luminance = 0.0, cct=cct)
                #self.set_light(luminance = 0.5, cct=cct)
            else:
                self.set_light(luminance=ratio * self.luminance,
                           cct=cct)
            time.sleep(3)
            chroma_lux = self.get_avg_luminance()
            if self.verbose > 0:
                print('Luminance avg measured: {}'.format(chroma_lux))
            ratio = self.abs_luminance / chroma_lux
            if prev_lum == self.luminance:
                break
            prev_lum = self.luminance
            max_iterations -= 1

    def set_light(self, luminance=None, cct=None, **kwargs):
        if self.selected_source != 'dummy' and  self.serial is None:
            self._open()

        if luminance is not None:
            self.luminance = luminance
        if cct:
            self.cct = cct
        if self.luminance > 1.0:
            self.luminance = 1.0
            if self.verbose > 0:
                print('Luminance intensity input capped to 1.0')

        # if self.verbose > 0:
            # print('Setting {} to CCT: {} and luminance: {}'.format(
            # self.selected_source, self.cct, self.luminance))
        self._mapping[self.selected_source](luminance=self.luminance, cct=self.cct, **kwargs)

    def print_chromameters(self):
        for name, cm in self.chromameters.items():
            print('Chromameter: {name}')
            for key, value in cm.items():
                print(f'\n{key}: {value}')

    def _set_light_arri(self, **kwargs):
        params = np.zeros(512, dtype=np.uint8)

        lum = np.round(kwargs['luminance'] * 65535)
        params[[0,1]] = lum // 256, lum % 256
        xy = xyofT(kwargs['cct'])
        if self.verbose > 1:
            print('Set arri at x: {}, y: {}'.format(*xy))
        xy = (xyofT(kwargs['cct']) / 0.8 * 65535).round().astype(np.uint16)
        params[[2,4]] = xy // 256
        params[[3,5]] = xy % 256
        serial_arr = [0x7E, 0x06, 0x01, 0x02, 0x0] + list(params) + [0xE7]
        # Do we need a sleep here?
        # time.sleep(0.5)
        self.serial.write(bytearray(serial_arr))
        time.sleep(0.05)

    def _set_light_iq_sol(self, **kwargs):
        if 'flicker_freq' in kwargs:
            if kwargs['flicker_freq'] in [0, 50, 60] + list(range(100, 1001, 50)):
                self.flicker_freq = kwargs['flicker_freq']
                # print('Flicker freq: {}'.format(self.flicker_freq))
            else:
                print('Flicker frequency {} NOT within limits: {}'.format(kwargs['flicker_freq'], [0, 50, 60] + list(range(100, 1001, 50))))
        else:
            self.flicker_freq = 0
        self._write_iq_sol()
        # Reset flicker_freq
        self.flicker_freq = 0

    def _set_light_dxo(self, **kwargs):
        self.serial.write

    def _write_iq_sol(self):
        try:
            msg = 'L {} T {} F {}'.format(int(self.luminance * 1000), int(self.cct), self.flicker_freq).encode()
            self.serial.write(msg)
        except serial.SerialException:
            raise serial.SerialException('Failed to write to serial port: {}'.format(self.port))

        self.timer = self.timeout
        while self.serial.in_waiting == 0 and self.timer > 0:
            time.sleep(0.001)
            self.timer -= 0.001
        ret = self.serial.read(self.serial.in_waiting)
        if b'SolBox' not in ret:
            raise Exception('Unexpected return from IQ Solution Box: {}'.format(ret))
        return True

    def __del__(self):
        if hasattr(self, 'serial') and self.serial is not None:
            self.serial.close()
        for name in self.chromameters:
            self.chromameters[name].__del__()


_tristimulus = np.array([
    [360, 0.000129900000000, 0.000003917000000, 0.000606100000000],
    [370, 0.000414900000000, 0.000012390000000, 0.001946000000000],
    [380, 0.001368000000000, 0.000039000000000, 0.006450001000000],
    [390, 0.004243000000000, 0.000120000000000, 0.020050010000000],
    [400, 0.014310000000000, 0.000396000000000, 0.067850010000000],
    [410, 0.043510000000000, 0.001210000000000, 0.207400000000000],
    [420, 0.134380000000000, 0.004000000000000, 0.645600000000001],
    [430, 0.283900000000000, 0.011600000000000, 1.385599999999999],
    [440, 0.348280000000000, 0.023000000000000, 1.747060000000000],
    [450, 0.336200000000000, 0.038000000000000, 1.772110000000000],
    [460, 0.290800000000000, 0.060000000000000, 1.669200000000000],
    [470, 0.195360000000000, 0.090980000000000, 1.287640000000000],
    [480, 0.095640000000000, 0.139020000000000, 0.812950100000000],
    [490, 0.032010000000000, 0.208020000000000, 0.465180000000000],
    [500, 0.004900000000000, 0.323000000000000, 0.272000000000000],
    [510, 0.009300000000000, 0.503000000000000, 0.158200000000000],
    [520, 0.063270000000000, 0.710000000000000, 0.078249990000000],
    [530, 0.165500000000000, 0.861999999999999, 0.042160000000000],
    [540, 0.290400000000000, 0.954000000000000, 0.020300000000000],
    [550, 0.433449900000000, 0.994950100000000, 0.008749999000000],
    [560, 0.594500000000000, 0.995000000000000, 0.003900000000000],
    [570, 0.762100000000000, 0.951999999999999, 0.002100000000000],
    [580, 0.916300000000000, 0.870000000000000, 0.001650001000000],
    [590, 1.026300000000000, 0.757000000000000, 0.001100000000000],
    [600, 1.062199999999999, 0.631000000000000, 0.000800000000000],
    [610, 1.002600000000000, 0.503000000000000, 0.000340000000000],
    [620, 0.854449900000000, 0.381000000000000, 0.000190000000000],
    [630, 0.642399999999999, 0.265000000000000, 0.000049999990000],
    [640, 0.447900000000000, 0.175000000000000, 0.000020000000000],
    [650, 0.283500000000000, 0.107000000000000, 0.000000000000000],
    [660, 0.164900000000000, 0.061000000000000, 0.000000000000000],
    [670, 0.087400000000000, 0.032000000000000, 0.000000000000000],
    [680, 0.046770000000000, 0.017000000000000, 0.000000000000000],
    [690, 0.022700000000000, 0.008210000000000, 0.000000000000000],
    [700, 0.011359160000000, 0.004102000000000, 0.000000000000000],
    [710, 0.005790346000000, 0.002091000000000, 0.000000000000000],
    [720, 0.002899327000000, 0.001047000000000, 0.000000000000000],
    [730, 0.001439971000000, 0.000520000000000, 0.000000000000000],
    [740, 0.000690078600000, 0.000249200000000, 0.000000000000000],
    [750, 0.000332301100000, 0.000120000000000, 0.000000000000000],
    [760, 0.000166150500000, 0.000060000000000, 0.000000000000000],
    [770, 0.000083075270000, 0.000030000000000, 0.000000000000000],
    [780, 0.000041509940000, 0.000014990000000, 0.000000000000000],
    [790, 0.000020673830000, 0.000007465700000, 0.000000000000000],
    [800, 0.000010253980000, 0.000003702900000, 0.000000000000000],
    [810, 0.000005085868000, 0.000001836600000, 0.000000000000000],
    [820, 0.000002522525000, 0.000000910930000, 0.000000000000000],
    [830, 0.000001251141000, 0.000000451810000, 0.000000000000000],
])

def wavelength_to_XYZ(wavelength, kind='cubic'):
    xyz = []
    for i in range(1,4):
        interp_fn = interp1d(_tristimulus[:,0], _tristimulus[:,i], kind = kind)
        xyz.append(interp_fn(wavelength))
    return np.array(xyz).T

class wavefunc(object):
    def __init__(self, wavelengths, values):
        self.wavelengths = wavelengths
        self.values = values

def clip_to_range(wave, wmin, wmax):
    approved = np.logical_and(wave.wavelengths >= wmin, wave.wavelengths <= wmax)
    wave.wavelengths = wave.wavelengths[approved]
    wave.values = wave.values[approved]
    return wave

def interp_waves(a,b):
    wavelengths = np.arange(max(a.wavelengths[0], b.wavelengths[0]), min(a.wavelengths[-1], b.wavelengths[-1])+1, 1)
    v_a = np.interp(wavelengths, a.wavelengths, a.values)
    v_b = np.interp(wavelengths, b.wavelengths, b.values)
    return wavefunc(wavelengths, v_a * v_b)

def wave_to_xyz(wave):
    wave = clip_to_range(wave, 360, 830)
    t_xyz = wavelength_to_XYZ(wave.wavelengths)
    interval = (wave.wavelengths[-1] - wave.wavelengths[0]) / (len(wave.wavelengths) -1)
    return wave.values.dot(t_xyz) * interval

def XYZofT(T, s=True):
    w = np.arange(300,800,5)*1e-9
    h = 6.62607015e-34
    c = 299792458.0
    k = 1.380649e-23
    v = c/w
    B = 8*np.pi * h * c / w**5 / (np.exp(h*c/k/T/w) - 1)
    Bo = wavefunc(w*1e9, B)
    xyz = wave_to_xyz(Bo)
    if s:
        return xyz/xyz[1]
    else:
        return xyz

def xyofT(T):
    xyz = XYZofT(T)
    return xyz[:2] / xyz.sum()

def list_light_sources():
    print('Types of lightsources, use option -s and any of:')
    for name in _DEVICE_CONFIG:
        print(f'\t{name}')

def main():
    import argparse
    try:
        from git_update import check_last_commit
        check_last_commit()
    except:
        None
    parser = argparse.ArgumentParser(description='IQ Solution Light box controller')
    parser.add_argument('--luminance', '-l', help='Luminance (Lux) to set in the box',
                                            type=float, default=None)
    parser.add_argument('--cct', '-t', help='CCT (K) to set in the box',
                                            type=int, default=None)
    parser.add_argument('--flicker_freq', '-F', help='Set frequency of flicker, solbox only', default=0, type=int)
    parser.add_argument('--port', '-p', help='Select serial port', type=str, default=None)
    parser.add_argument('--light_source', '-s', help='Device type of light source\n'
        'Options ', type=str, default=None)
    parser.add_argument('--list_light_sources', '-L', help='List available light source options', default=False, action='store_true')
    parser.add_argument('--chromameter_readback', '-C', help='Print the readings from chromameters if available', action='store_true', default=False)
    parser.add_argument('--calibrated', '-c', help='Use luxmeter to calibrate', action='store_true', default=False)
    parser.add_argument('--tolerance', help='Tolerance when using calibration mode 0.01 is default',
                        default=0.01, type=float)
    parser.add_argument('--verbose', '-v', help='Verbose level', default=1, type=int)
    parser.add_argument('--dummy', help='Set this to simulate specific light type', default=False, action='store_true')

    args = parser.parse_args()
    if (args.light_source is not None and args.light_source not in _DEVICE_CONFIG):
        list_light_sources()
        print(f'\n\t--light_source option "{args.light_source}" not valid selection from above list.')
        return

    if args.list_light_sources:
        list_light_sources()
        return

    light = light_source(port=args.port, light_source=args.light_source, verbose=args.verbose, dummy=args.dummy)
    if args.calibrated:
        light.set_light_abs(abs_luminance=args.luminance, cct=args.cct, tolerance=args.tolerance, verbose=args.verbose, flicker_freq=args.flicker_freq)
    else:
        light.set_light(luminance=args.luminance, cct=args.cct, verbose=args.verbose, flicker_freq=args.flicker_freq)
    if args.chromameter_readback:
        time.sleep(2)
        print("Here")
        light.print_chromameters()
    light.__del__()

if __name__ == '__main__':
    main()
