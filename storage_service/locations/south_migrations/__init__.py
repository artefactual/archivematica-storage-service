# South logging improperly configured
# Fix from http://stackoverflow.com/questions/8578223/how-to-disable-south-debug-logging-in-django
from __future__ import absolute_import
import logging

south_logger = logging.getLogger("south")
south_logger.setLevel(logging.INFO)
