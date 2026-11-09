"""One family of errors. The server turns every one of them into a tool error
whose message tells the agent what happened and what it can do next."""


class AndroidTestError(Exception):
    """Base class: anything the agent should read as a refused or failed call."""


class Refused(AndroidTestError):
    """A safety lock said no: device, package, path or argument not allowed."""


class Busy(AndroidTestError):
    """Another heavy job (install, test run) holds the lock."""


class DeviceError(AndroidTestError):
    """adb or flutter answered, but not what was expected."""


class TargetNotFound(AndroidTestError):
    """No element on screen matches the label."""


class AmbiguousTarget(AndroidTestError):
    """More than one element matches the label: tapping one would be a guess."""
