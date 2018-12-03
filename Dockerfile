FROM hypriot/rpi-alpine

RUN apk add \
	linux-headers \
	gcc \
	musl-dev \
	jpeg-dev \
	zlib-dev \
	freetype-dev \
	python \
    python-dev \
    py-pip \
  && rm -rf /var/cache/apk/*

WORKDIR /usr/src/app

RUN pip install --no-cache-dir rpi.gpio numpy spidev pillow

COPY . ./

CMD ["python", "./main.py"]
