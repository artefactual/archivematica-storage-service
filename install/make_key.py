#update django secret key
#syncdb
#collectstatic
#fix perms
#restart nginx and uwsgi

import os, hashlib

def gen():
    return hashlib.sha1(os.urandom(512)).hexdigest()

myhash = gen()
print myhash

