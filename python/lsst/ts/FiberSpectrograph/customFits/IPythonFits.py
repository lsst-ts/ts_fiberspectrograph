from abc import ABC, abstractmethod


class IPythonFits(ABC):

    def __init__(self):
        self.path = ""
        self.filename = ""

    def setFilename(self, path, filename):
        self.path = path
        self.filename = filename

    @abstractmethod
    def saveToFile(self):
        pass

    @abstractmethod
    def openFile(self):
        pass

    @abstractmethod
    def getFileSize(self):
        pass

    @abstractmethod
    def closeFile(self):
        pass

    @abstractmethod
    def addHeader(self, keyName, value, comment):
        pass

    @abstractmethod
    def addData(self, values):
        pass
