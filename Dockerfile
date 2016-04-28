FROM python:2.7

ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /src

WORKDIR /src/storage_service

RUN apt-get update \
	&& apt-get --yes install unar rsync mysql-client \
	&& apt-get clean \
	&& rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

COPY ./requirements /src/requirements
RUN pip install -r /src/requirements/production.txt

COPY . /src
