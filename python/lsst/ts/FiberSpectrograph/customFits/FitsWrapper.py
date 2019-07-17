from astropy.io import fits
from os import path
from hashlib import md5

class PythonFits(object):

    def __init__(self, path, filename, separator='/'):
        self.path = path
        self.filename = filename
        self.separator = separator
        self.file = fits.HDUList()
        self.hdu = fits.PrimaryHDU()

    def setFilename(self, path, filename):
        self.path = path
        self.filename = filename

    def saveToFile(self):
        self.file.writeto(self.path+"/"+self.filename+".fits", overwrite=True)

    def openFile(self):
        self.file = fits.open(self.path+"/"+self.filename+".fits")

    def getFileSize(self):
        return path.getsize(self.path+"/"+self.filename+".fits")

    def closeFile(self):
        # Close the file and returns the checksum
        self.file.close()

    def getChecksum(self):
        # File shouldn't be open
        fitsFile = open(self.path+"/"+self.filename+".fits", "rb")
        checksum = md5(fitsFile.read()).hexdigest()
        fitsFile.close()
        return checksum

    def addHeader(self, keyName, value, comment):
        # Add header to the file: header['keyName'] = 'value'
        # Add a new 'comment' keyword
        self.hdu.header.append((keyName, value, comment))
        self.file = fits.HDUList([self.hdu])

    def addData(self, values):
        self.hdu.data = values
        self.file = fits.HDUList([self.hdu])


if __name__ == "__main__":

    pass
