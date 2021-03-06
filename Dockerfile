FROM bboerst/rpi-qemu-alpine-python:2

RUN apk add --no-cache \
	linux-headers \
	gcc \
	musl-dev \
	jpeg-dev \
	zlib-dev \
	freetype-dev \
	py-numpy

WORKDIR /usr/src/app

RUN pip install --no-cache-dir rpi.gpio spidev pillow

COPY . ./

CMD ["python", "./main.py"]
