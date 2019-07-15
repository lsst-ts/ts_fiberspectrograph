import unittest
import numpy as np
import os.path

from lsst.utils import getPackageDir

from lsst.ts.FiberSpectrograph.customFits.PythonFits import PythonFits


class TestFitsFile(unittest.TestCase):

    def setUp(self):
        modulePath = getPackageDir("ts_FiberSpectrograph")
        dataFolder = os.path.join(modulePath, "tests", "testData")
        self.fitsFile = PythonFits(dataFolder, "testFits", separator='/')

    def test_addDataAndCloseFile(self):
        data = np.arange(100.0)
        self.fitsFile.addData(data)
        self.fitsFile.closeFile()

    def test_testChecksum(self):
        a = len(self.fitsFile.getChecksum())
        self.assertGreater(a, 1)


if __name__ == "__main__":

    unittest.main()
