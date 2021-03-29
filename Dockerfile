FROM python:3.9-alpine3.13

ARG UID=1000

RUN apk --no-cache add zip

ADD ./requirements.txt /app/requirements.txt
WORKDIR /app

RUN apk add --virtual .build-deps --no-cache --update cmake make musl-dev gcc g++ gettext-dev libintl git && \
    rm -rf musl-locales && \
    pip3 install -r requirements.txt && \
    apk del .build-deps && \
    adduser \
    --disabled-password \
    --no-create-home \
    --shell /bin/bash \
    --gecos "" \
    --uid ${UID} \
    --home /app \
    app && \
    chown -R app:app /app

ADD . /app

USER app
EXPOSE 8080

CMD ["python", "server.py"]
