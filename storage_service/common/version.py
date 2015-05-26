
STORAGE_SERVICE_VERSION = (0, 7, 0)

def get_version():
    """ Returns the version number as a string. """
    # Inspired by Django's get_version
    version = STORAGE_SERVICE_VERSION
    parts = 2 if version[2] == 0 else 3
    main = '.'.join(str(x) for x in version[:parts])
    return main
