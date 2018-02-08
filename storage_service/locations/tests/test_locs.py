import os

# Find the our cwd and then augment the path to point to fixtures. The path
# should look something like src/storage-service/locations/tests/fixtures. This
# folder is where the storage service tests will read from. 
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_READ_DIR = os.path.abspath(os.path.join(THIS_DIR, '..', 'fixtures', ''))

# The storage services tests require a location to write to. We do that here. 
FIXTURES_WRITE_DIR = "/tmp/archivematica/fixtures/"

# Implementation specific 
ARKIVUM_WRITE_DIR = os.path.abspath(os.path.join(FIXTURES_WRITE_DIR, 'arkivum'))

def __init__():
	if not os.path.isdir(FIXTURES_WRITE_DIR):
		mkdir_p(FIXTURES_WRITE_DIR)

def mkdir_p(path):
 	try:
		os.makedirs(path)
	except OSError as exc:  # Python >2.5
		if exc.errno == errno.EEXIST and os.path.isdir(path):
			pass
		else:
			raise