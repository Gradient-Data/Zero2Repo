# feature: F17
"""Independent Fourier integrals of steady periodic waveforms."""
import numpy as np
from scipy.integrate import quad


def harmonic_reference(kind, amplitude, size, threshold=None):
    """Integrate prescribed output waveforms for a cosine excitation."""
    a = amplitude
    if kind == 'relay':
        if a < threshold:
            return complex(np.nan)
        lag = np.arcsin(threshold/a)
        breaks = [lag + np.pi/2, lag + 3*np.pi/2]
        def wave(t):
            return size if np.cos(t-lag) > 0 else -size
    elif kind == 'backlash':
        h = size/2
        if a <= h:
            return 0j
        turn = np.arccos(1-size/a)
        breaks = [turn, np.pi, np.pi+turn]
        def wave(t):
            return (min(a-h, a*np.cos(t)+h) if t <= np.pi
                    else max(-a+h, a*np.cos(t)-h))
    elif kind == 'saturation':
        breaks = []
        if a > size:
            angle = np.arccos(size/a)
            breaks = [angle, np.pi-angle, np.pi+angle, 2*np.pi-angle]
        def wave(t):
            return np.clip(a*np.cos(t), -size, size)
    else:
        raise ValueError('Unknown waveform')
    real = quad(lambda t: wave(t)*np.cos(t), 0, 2*np.pi,
                points=breaks, epsabs=1e-10)[0]
    imag = quad(lambda t: -wave(t)*np.sin(t), 0, 2*np.pi,
                points=breaks, epsabs=1e-10)[0]
    return (real+1j*imag)/(np.pi*a)
