:Authors:
    Justin Simpson
    Holly Becker

Install
=========

This app is designed to be run using pip + virtualenv + virtualenvwrapper.
Tested with python 2.7.3.

To get up and running:

* install pip (if it is not already there)

::
    $ sudo apt-get install python-pip

* install some dependencies (if they are not already installed)

::
    $ sudo apt-get install gcc libxslt1-dev python-dev

* install virtualenv and virtualenvwrapper

::

    $ pip install virtualenv virtualenvwrapper

* add some environment variables to your shell startup script, such as .bashrc.

This allows pip and virtualenv and virtualenvwrapper to do their magic.
The exact location of the virtualenvwrapper.sh script might be different on your system.

::

    export WORKON_HOME=$HOME/Envs
    source /usr/local/bin/virtualenvwrapper.sh

* create and configure the virtualenv, and add source code

::

    mkdir -p $WORKON_HOME
    mkvirtualenv storage-service
    git clone git@git.artefactual.com:archivematica-storage-service.git
    cd archivematica-storage-service
    setvirtualenvproject

You should now have a virtualenv, with it's own isolated python interpreter, and a project directory.
The source code for the project should be there ready to work with.

* Add dependencies.  Assuming you are doing development work, use the local requirements file.

::
    pip install -r requirements/local.txt

* Create required environment variables. Add the following to your virtualenv's postactivate script, found in this example at $WORKON_HOME/storage-service/bin/postactivate.

::

    PROJECTPATH=$(cat $VIRTUAL_ENV/.project)
    export PYTHONPATH=$PYTHONPATH:$PROJECTPATH

    export DJANGO_SETTINGS_MODULE=storage_service.settings.local
    export DJANGO_SECRET_KEY='ADDKEY'
    export SS_DB_NAME='storage_service/default.db'
    export SS_DB_USER=''
    export SS_DB_PASSWORD=''
    export SS_DB_HOST=''

Change the DJANGO_SETTINGS_MODULE to match whichever requirements file you installed from.

* Create the database schema. You can use the django-admin script to make an initial version of the main database, then use the tool South to create the fpr app's data model.  

::

    cdproject
    cd storage_service
    python2 manage.py syncdb

* Start the server.  This example uses Django's built in webserver, good for testing only.  Use a WSGI compliant webserver like Apache or Nginx in production.

::

    cdproject
    cd storage_service
    python2 manage.py runserver 0.0.0.0:8000

Using 0.0.0.0 makes the app available on all interfaces.
