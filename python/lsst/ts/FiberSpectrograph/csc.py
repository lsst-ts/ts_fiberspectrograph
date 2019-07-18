import asyncio
import traceback
import enum
import pathlib
import numpy as np

from lsst.ts.FiberSpectrograph.model import FiberSpec

from lsst.ts.salobj import base_csc, ConfigurableCsc, Remote, State

class DetailedState(enum.IntEnum):
    """ For the FiberSpectrograph, detailed state indicate if the instrument
        is IMAGING i.e. capturing a spectrum or NOTIMAGING i.e idle 
        possible detailed states:
        NOTIMAGING: Available to take a spectrum on receiving a 
        CaptureSpectImage command
        IMAGING: Currently taking an image and will reject any incoming 
        CaptureSpectImage command
    """
    NOTIMAGING = 1
    IMAGING = 2
    

class FiberSpectrograph(ConfigurableCsc)
    """Configurable Commandable SAL Component (CSC) for the Fiber Spectrograph
    """
    def _init_(self, index, config_dir=None, initial_state=State.STANDBY):
        """
        Initialize FiberSpectrograph CSC.
        """
        schema_path = pathlib.Path(__file__).resolve().parents[4].joinpath(
            "schema", "fiberspectrograph.yaml")

        super().__init__("FiberSpectrograph", index=index, 
            schema_path=schema_path, config_dir=config_dir, 
            initial_state=initial_state) 
            # initial_simulation_mode=initial_simulation_mode)

        self._detailed_state = DetailedState.NOTIMAGING


    def detailed_state(self):
        """Return the current value for detailed state.
        Returns
        -------
        detailed_state : np.uint8
        """
        return np.uint8(self._detailed_state)


    def detailed_state(self, value):
        """Set and publish current value for detailed state.
        Parameters
        ----------
        value : `int`
            New detailed state. Will be converted to np.uint8
        """
        self._detailed_state = np.uint8(value)
        self.evt_detailedState.set_put(substate=self._detailed_state)

    async def begin_enable(self):
        self.model = FiberSpecTest()

    async def do_captureSpectImage(self, data):
        self.assert_enable("captureSpectImage")
        self.assert_detailed("")
        await self.model.captureSpectImage()

    def assert_detailed(self):
        pass


    def get_config_pkg():
        return "ts_config_attcs"

    async def configure(self, config):
        """Implement method to configure the CSC.
        Parameters
        ----------
        config : `object`
            The configuration as described by the schema at ``schema_path``,
            as a struct-like object.
        Notes
        -----
        Called when running the ``start`` command, just before changing
        summary state from `State.STANDBY` to `State.DISABLED`.
        """

        pass

