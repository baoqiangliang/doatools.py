from enum import Enum
from abc import ABC, abstractmethod
import numpy as np
import scipy

class SourcePlacement(ABC):
    '''
    Represents the placement of several sources.

    Subclass notice: the __init__ should take only two parameters: locations and
    unit.
    '''

    def __init__(self, locations, units):
        self._locations = locations
        self._unit = units

    def __len__(self):
        '''
        Returns the number of sources.
        '''
        return self._locations.shape[0]

    def __getitem__(self, key):
        '''
        Accesses a specific source location or obtains a subset of source
        placement via slicing.

        Implementation notice: this is a generic implementation. If your
        subclass's __init__ accepts additional arguments other than locations,
        you should override this default implementation.

        Args:
            key : An integer, slice, or 1D numpy array of indices/boolean masks.
        '''
        if np.isscalar(key):
            return self._locations[key]
        if isinstance(key, list) or isinstance(key, slice):
            locations = self._locations[key]
        elif isinstance(key, np.ndarray):
            if key.ndim != 1:
                raise ValueError('1D array expected.')
            locations = self._locations[key]
        else:
            raise KeyError('Unsupported index.')
        return type(self)(locations, self._unit)

    @property
    def n_sources(self):
        '''
        Retrieves the number of sources.
        '''
        return len(self)

    @property
    def locations(self):
        '''
        Retrives the source locations. Do NOT modify.
        '''
        return self._locations

    @property
    def unit(self):
        '''
        Retrives the unit used.
        '''
        return self._unit

    @abstractmethod
    def phase_delay_matrix(self, sensor_locations, wavelength, derivatives=False):
        '''
        Computes the M x K phase delay matrix D where D[m,k] is the relative
        phase delay between the m-th sensor and the k-th source (usually using
        the first sensor as the reference).

        Notes: the phase delay matrix is used in constructing the steering
        matrix. This method is decoupled from the steering matrix method
        because the phase delays are calculated differently for different
        types of sources (e.g. far-field vs. near-field).

        Args:
            sensor_locations: An M x d (d = 1, 2, 3) matrix representing the
                sensor locations using the Cartesian coordinate system.
            wavelength: Wavelength of the carrier wave.
            derivatives: If set to true, also outputs the derivative matrix (or
                matrices) with respect to the source locations. Default value
                is False.
        '''
        pass

class FarField1DSourcePlacement(SourcePlacement):

    def __init__(self, locations, unit='rad'):
        r'''
        Creates a far-field 1D source placement.

        Args:
            locations: A list or 1D numpy array representing the source
                locations.
            unit: Can be 'rad', 'deg' or 'sin'. 'sin' is a special unit where
                sine of the arrival angle is used instead of the arrival angle
                itself. 
        '''
        if isinstance(locations, list):
            locations = np.array(locations)
        if locations.ndim > 1:
            raise ValueError('1D numpy array expected.')
        valid_units = ['rad', 'deg', 'sin']
        if unit not in valid_units:
            raise ValueError('Unit can only be one of the following: {0}.'.format(', '.join(valid_units)))
        super().__init__(locations, unit)

    def phase_delay_matrix(self, sensor_locations, wavelength, derivatives=False):
        '''
        Computes the M x K phase delay matrix D where D[m,k] is the relative
        phase delay between the m-th sensor and the k-th far-field source
        (usually using the first sensor as the reference).

        Args:
            sensor_locations: An M x d (d = 1, 2, 3) matrix representing the
                sensor locations using the Cartesian coordinate system. When the
                sensor locations are 2D or 3D, the DOAs are assumed to be within
                the xy-plane.
            wavelength: Wavelength of the carrier wave.
            derivatives: If set to true, also outputs the derivative matrix (or
                matrices) with respect to the source locations. Default value
                is False.
        '''
        if sensor_locations.shape[1] < 1 or sensor_locations.shape[1] > 3:
            raise ValueError('Sensor locations can only consists of 1D, 2D or 3D coordinates.')
        
        if self._unit == 'sin':
            return self._phase_delay_matrix_sin(sensor_locations, wavelength, derivatives)
        else:
            return self._phase_delay_matrix_rad(sensor_locations, wavelength, derivatives)
        
    def _phase_delay_matrix_rad(self, sensor_locations, wavelength, derivatives=False):
        # Unit can only be 'rad' or 'deg'.
        # Unify to radians.
        if self._unit == 'deg':
            locations = np.deg2rad(self._locations)
        else:
            locations = self._locations
        # Locations is an 1D vector, convert it to a one-row matrix.
        locations = locations[np.newaxis]
        s = 2 * np.pi / wavelength
        if sensor_locations.shape[1] == 1:
            D = s * sensor_locations * np.sin(locations)
            if derivatives:
                DD = s * sensor_locations * np.cos(locations)
        else:
            # The sources are assumed to be within the xy-plane. The offset
            # along the z-axis of the sensors does not affect the delays.
            D = s * (sensor_locations[:, 0] * np.sin(locations) +
                        sensor_locations[:, 1] * np.cos(locations))
            if derivatives:
                DD = s * (sensor_locations[:, 0] * np.cos(locations) -
                            sensor_locations[:, 1] * np.sin(locations))
        return (D, DD) if derivatives else D

    def _phase_delay_matrix_sin(self, sensor_locations, wavelength, derivatives=False):
        # Locations is an 1D vector, convert it to a one-row matrix.
        sin_vals = self._locations[np.newaxis]
        s = 2 * np.pi / wavelength
        if sensor_locations.shape[1] == 1:
            D = s * sensor_locations * sin_vals
            if derivatives:
                # Note that if x = \sin\theta then
                # \frac{\partial cx}{\partial x} = cx
                # This is difference from the derivative w.r.t. \theta:
                # \frac{\partial cx}{\partial \theta} = c\cos\theta
                DD = np.tile(s * sensor_locations, (1, self._locations.size))
        else:
            # The sources are assumed to be within the xy-plane. The offset
            # along the z-axis of the sensors does not affect the delays.
            cos_vals = np.sqrt(1.0 - sin_vals * sin_vals)
            D = s * (sensor_locations[:, 0] * sin_vals +
                        sensor_locations[:, 1] * cos_vals)
            if derivatives:
                # If x = \sin\theta, \theta \in (-\pi/2, \pi/2)
                # a \sin\theta + b \cos\theta = ax + b\sqrt{1-x^2}
                DD = s * (sensor_locations[:, 0] -
                            sensor_locations[:, 1] * sin_vals / cos_vals)
        return (D, DD) if derivatives else D


class FarField2DSourcePlacement(SourcePlacement):

    def __init__(self, locations, unit='rad'):
        '''
        Creates a far-field 2D source placement.

        Args:
            locations: An K x 2  numpy array representing the source locations,
                where K is the number of sources. Should never be modified after
                creation.
            unit: Can be 'rad' or 'deg'.
        '''
        if isinstance(locations, list):
            locations = np.array(locations)
        if locations.ndim != 2 or locations.shape[1] != 2:
            raise ValueError('Expecting an N x 2 numpy array.')
        valid_units = ['rad', 'deg']
        if unit not in valid_units:
            raise ValueError('Unit can only be one of the following: {0}.'.format(', '.join(valid_units)))
        super().__init__(locations, unit)

    def phase_delay_matrix(self, sensor_locations, wavelength, derivatives=False):
        '''
        Computes the M x K phase delay matrix D where D[m,k] is the relative
        phase delay between the m-th sensor and the k-th far-field source
        (usually using the first sensor as the reference).

        Args:
            sensor_locations: An M x d (d = 1, 2, 3) matrix representing the
                sensor locations using the Cartesian coordinate system. Linear
                arrays (1D arrays) are assumed to be placed along the x-axis.
            wavelength: Wavelength of the carrier wave.
            derivatives: If set to true, also outputs the derivative matrix (or
                matrices) with respect to the source locations. Default value
                is False.
        '''
        if sensor_locations.shape[1] < 1 or sensor_locations.shape[1] > 3:
            raise ValueError('Sensor locations can only consists of 1D, 2D or 3D coordinates.')
        
        if derivatives:
            raise ValueError('Derivative matrix computation is not supported for far-field 2D DOAs.')

        # Unify to radians.
        if self._unit == 'deg':
            locations = np.deg2rad(self._locations)
        else:
            locations = self._locations
        
        s = 2 * np.pi / wavelength
        cos_el = np.cos(locations[:, 1]).T
        if sensor_locations.shape[1] == 1:
            # Linear arrays are assumed to be placed along the x-axis
            D = s * sensor_locations * (cos_el * np.cos(locations[:, 0]).T)
        else:
            cc = cos_el * np.cos(locations[:, 0]).T
            cs = cos_el * np.sin(locations[:, 1]).T
            if sensor_locations.shape[1] == 2:
                D = s * (sensor_locations[:, 0] * cc +
                            sensor_locations[:, 1] * cs)
            else:
                D = s * (sensor_locations[:, 0] * cc +
                            sensor_locations[:, 1] * cs +
                            sensor_locations[:, 2] * np.sin(locations[:, 1]).T)
        
        return D
