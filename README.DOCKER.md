## Docker and Docker Compose

Clone the repository:

    $ git clone --recursive https://github.com/archivematica/archivematica-storage-service
    $ cd archivematica-storage-service

Build the images and start services:

    $ docker-compose build
    $ docker-compose up -d

Migrate the database:

    # Percona may not become available until a few minutes after starting
    $ docker-compose exec storage_service ./manage.py migrate

Collect static assets:

    $ docker-compose exec storage_service ./manage.py collectstatic --noinput

Restart SS services:

    $ docker-compose restart storage_service storage_service_worker

Check status and discover published port by Nginx:

    $ docker-compose ps

Test that dynamic content is being served:

    $ curl -Lv 127.0.0.1:32781

Test static content

    $ curl -Lv 127.0.0.1:32781/static/js/project.js

Do you want to start over? Delete **everything**.

    $ docker-compose down --volumes
